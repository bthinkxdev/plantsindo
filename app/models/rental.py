from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from .base import TimeStampedModel


class RentalConfig(TimeStampedModel):
    """
    Dedicated rental configuration for a product (simple or combo).

    This intentionally keeps rental data out of Product core fields.
    """

    product = models.OneToOneField('Product', on_delete=models.CASCADE, related_name='rental_config')
    is_rent_enabled = models.BooleanField(default=False, db_index=True)
    rent_price_per_day = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    rent_description = models.CharField(max_length=500, blank=True)
    rent_instructions = models.TextField(blank=True)

    class Meta:
        ordering = ('-updated_at', '-created_at')
        indexes = [models.Index(fields=['is_rent_enabled'])]

    def __str__(self):
        return f'RentalConfig(product_id={self.product_id}, enabled={self.is_rent_enabled})'


class RentalBooking(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = ('pending', 'Pending')
        ACTIVE = ('active', 'Active')
        COMPLETED = ('completed', 'Completed')
        RETURNED = ('returned', 'Returned')
        CANCELLED = ('cancelled', 'Cancelled')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='rental_bookings')
    product = models.ForeignKey('Product', on_delete=models.PROTECT, related_name='rental_bookings')
    order_item = models.OneToOneField('OrderItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='rental_booking')

    rental_start_date = models.DateField(db_index=True)
    rental_end_date = models.DateField(db_index=True)
    total_days = models.PositiveIntegerField()

    price_per_day = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    damage_fee = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    return_condition_notes = models.TextField(blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['product', 'status', 'rental_start_date', 'rental_end_date']),
            models.Index(fields=['status', 'rental_start_date']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(rental_end_date__gte=models.F('rental_start_date')), name='rentalbooking_end_gte_start'),
            models.CheckConstraint(condition=models.Q(total_days__gte=1), name='rentalbooking_days_positive'),
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name='rentalbooking_amount_nonneg'),
        ]

    def __str__(self):
        return f'RentalBooking(product_id={self.product_id}, {self.rental_start_date}→{self.rental_end_date}, status={self.status})'

    def mark_active(self):
        if self.status != self.Status.ACTIVE:
            self.status = self.Status.ACTIVE
            self.activated_at = timezone.now()

    def mark_returned(self, *, condition_notes: str = '', damage_fee=None):
        self.status = self.Status.RETURNED
        self.return_condition_notes = condition_notes or self.return_condition_notes
        if damage_fee is not None:
            self.damage_fee = damage_fee
        self.returned_at = timezone.now()

    def mark_cancelled(self):
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()

