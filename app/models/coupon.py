"""
Coupon models — cart-wide promotional codes.

Coupon           — code + discount rules + usage limits + validity window.
CouponRedemption — one row per successful order that used a coupon.
"""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .base import TimeStampedModel


class Coupon(TimeStampedModel):
    class DiscountType(models.TextChoices):
        PERCENT = ('percent', 'Percentage')
        FIXED = ('fixed', 'Fixed amount')

    code = models.CharField(max_length=40, unique=True, db_index=True)
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT,
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Percent (0–100) or fixed ₹ amount.',
    )
    min_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Minimum merchandise subtotal required.',
    )
    max_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Optional cap for percentage coupons.',
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Global redemption limit. Blank = unlimited.',
    )
    max_uses_per_customer = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Per-customer limit. Use 1 for one-time. Blank = unlimited.',
    )
    times_redeemed = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True, default='')
    internal_note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class CouponRedemption(TimeStampedModel):
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        related_name='redemptions',
    )
    order = models.OneToOneField(
        'Order',
        on_delete=models.CASCADE,
        related_name='coupon_redemption',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coupon_redemptions',
    )
    email = models.EmailField(blank=True, default='', db_index=True)
    phone = models.CharField(max_length=20, blank=True, default='', db_index=True)
    code_snapshot = models.CharField(max_length=40)
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code_snapshot} → {self.order_id}'
