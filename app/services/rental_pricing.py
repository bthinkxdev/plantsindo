from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError


def _d(val) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return None


def get_rental_config(product):
    cfg = getattr(product, 'rental_config', None)
    return cfg


def compute_rental_line_unit_price(product, *, days: int) -> Decimal:
    """
    Compute rental line unit price for a product using RentalConfig.

    Rentals are priced per-day and stored as a single unit_price for the cart line.
    """
    if not getattr(product, 'is_rent_available', False):
        raise ValidationError('This product is not available for rent.')
    cfg = get_rental_config(product)
    if not cfg or not getattr(cfg, 'is_rent_enabled', False):
        raise ValidationError('Rental is not enabled for this product.')
    try:
        d = int(days)
    except (TypeError, ValueError):
        raise ValidationError('Invalid rental duration.') from None
    if d < 1:
        raise ValidationError('Invalid rental duration.')
    rate = _d(getattr(cfg, 'rent_price_per_day', None))
    if rate is None or rate < 0:
        raise ValidationError('Rental rate is not configured.')
    return rate * d


def rental_key(days: int) -> str:
    return f'day:{int(days)}'

