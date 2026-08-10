"""
CouponService — single source of truth for checkout coupon validation & discount.

validate_for_checkout(...) → CouponValidationResult | raises CouponError
compute_discount(coupon, subtotal) → Decimal (capped at subtotal)
record_redemption(...) → CouponRedemption (increments Coupon.times_redeemed)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from app.models import Coupon, CouponRedemption

ZERO = Decimal('0.00')
TWOPLACES = Decimal('0.01')


class CouponError(Exception):
    """Stable coupon validation failure for forms / API."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class CouponValidationResult:
    coupon: Coupon
    code: str
    discount_amount: Decimal
    message: str = ''


def normalize_code(code) -> str:
    return (code or '').strip().upper()


def normalize_email(email) -> str:
    return (email or '').strip().lower()


def normalize_phone(phone) -> str:
    digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def _as_decimal(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def get_coupon(code: str) -> Optional[Coupon]:
    normalized = normalize_code(code)
    if not normalized:
        return None
    return Coupon.objects.filter(code=normalized).first()


def is_currently_valid(coupon: Coupon, now=None) -> tuple[bool, str]:
    """Return (ok, error_code). error_code empty when ok."""
    if not coupon.is_active:
        return False, 'inactive'
    now = now or timezone.now()
    if coupon.starts_at and now < coupon.starts_at:
        return False, 'not_started'
    if coupon.ends_at and now > coupon.ends_at:
        return False, 'expired'
    if coupon.max_uses is not None and coupon.times_redeemed >= coupon.max_uses:
        return False, 'exhausted'
    return True, ''


def compute_discount(coupon: Coupon, subtotal) -> Decimal:
    """
    Discount from merchandise subtotal only.
    Never exceeds subtotal (shipping / GST not coupon-funded).
    """
    sub = _as_decimal(subtotal)
    if sub <= ZERO:
        return ZERO
    if coupon.min_order_amount and sub < _as_decimal(coupon.min_order_amount):
        return ZERO

    if coupon.discount_type == Coupon.DiscountType.PERCENT:
        raw = (sub * _as_decimal(coupon.value) / Decimal('100')).quantize(
            TWOPLACES, rounding=ROUND_HALF_UP
        )
        if coupon.max_discount_amount is not None:
            raw = min(raw, _as_decimal(coupon.max_discount_amount))
    else:
        raw = _as_decimal(coupon.value)

    return min(raw, sub).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def customer_redemption_count(
    coupon: Coupon,
    *,
    user=None,
    email: str = '',
    phone: str = '',
) -> int:
    qs = CouponRedemption.objects.filter(coupon=coupon)
    clauses = Q()
    if user is not None and getattr(user, 'is_authenticated', False) and getattr(user, 'pk', None):
        clauses |= Q(user_id=user.pk)
    email_n = normalize_email(email)
    if email_n:
        clauses |= Q(email__iexact=email_n)
    phone_n = normalize_phone(phone)
    if phone_n:
        clauses |= Q(phone=phone_n)
    if not clauses:
        return 0
    return qs.filter(clauses).count()


_ERROR_MESSAGES = {
    'not_found': 'Invalid coupon code.',
    'inactive': 'This coupon is no longer active.',
    'not_started': 'This coupon is not active yet.',
    'expired': 'This coupon has expired.',
    'exhausted': 'This coupon has reached its usage limit.',
    'min_order': 'Order does not meet the minimum amount for this coupon.',
    'customer_limit': 'You have already used this coupon.',
    'zero_discount': 'This coupon does not apply to the current order.',
}


def validate_for_checkout(
    code: str,
    *,
    subtotal,
    user=None,
    email: str = '',
    phone: str = '',
    now=None,
) -> CouponValidationResult:
    normalized = normalize_code(code)
    if not normalized:
        raise CouponError('not_found', _ERROR_MESSAGES['not_found'])

    coupon = get_coupon(normalized)
    if not coupon:
        raise CouponError('not_found', _ERROR_MESSAGES['not_found'])

    ok, err = is_currently_valid(coupon, now=now)
    if not ok:
        raise CouponError(err, _ERROR_MESSAGES.get(err, 'Invalid coupon.'))

    sub = _as_decimal(subtotal)
    if coupon.min_order_amount and sub < _as_decimal(coupon.min_order_amount):
        min_amt = _as_decimal(coupon.min_order_amount)
        raise CouponError(
            'min_order',
            f'Minimum order of ₹{min_amt.quantize(TWOPLACES)} required for this coupon.',
        )

    if coupon.max_uses_per_customer is not None:
        used = customer_redemption_count(
            coupon, user=user, email=email, phone=phone
        )
        if used >= coupon.max_uses_per_customer:
            raise CouponError('customer_limit', _ERROR_MESSAGES['customer_limit'])

    discount = compute_discount(coupon, sub)
    if discount <= ZERO:
        raise CouponError('zero_discount', _ERROR_MESSAGES['zero_discount'])

    return CouponValidationResult(
        coupon=coupon,
        code=coupon.code,
        discount_amount=discount,
        message=f'{coupon.code} applied (−₹{discount})',
    )


@transaction.atomic
def record_redemption(
    order,
    coupon: Coupon,
    discount_amount,
    *,
    user=None,
    email: str = '',
    phone: str = '',
) -> CouponRedemption:
    locked = Coupon.objects.select_for_update().get(pk=coupon.pk)
    ok, err = is_currently_valid(locked)
    if not ok:
        raise CouponError(err, _ERROR_MESSAGES.get(err, 'Invalid coupon.'))
    if locked.max_uses_per_customer is not None:
        used = customer_redemption_count(
            locked, user=user, email=email, phone=phone
        )
        if used >= locked.max_uses_per_customer:
            raise CouponError('customer_limit', _ERROR_MESSAGES['customer_limit'])

    redemption = CouponRedemption.objects.create(
        coupon=locked,
        order=order,
        user=user if user is not None and getattr(user, 'pk', None) else None,
        email=normalize_email(email),
        phone=normalize_phone(phone),
        code_snapshot=locked.code,
        discount_amount=_as_decimal(discount_amount),
    )
    Coupon.objects.filter(pk=locked.pk).update(
        times_redeemed=models.F('times_redeemed') + 1
    )
    return redemption
