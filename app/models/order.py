import logging

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .base import TimeStampedModel
from .combo import Combo
from .product import Product, Variant

logger = logging.getLogger(__name__)


class Address(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='addresses')
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address_line = models.TextField()
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False, db_index=True)
    is_snapshot = models.BooleanField(default=False, db_index=True)

    delivery_state = models.ForeignKey(
                    'DeliveryState',
                    on_delete=models.SET_NULL,
                    null=True,
                    blank=True,
                    related_name='addresses',
                )

    class Meta:
        indexes = [models.Index(fields=['user', 'is_default'])]

    def __str__(self):
        return f'{self.full_name} - {self.city}'


class Order(TimeStampedModel):

    class Status(models.TextChoices):
        PLACED = ('placed', 'Placed')
        CONFIRMED = ('confirmed', 'Confirmed')
        SHIPPED = ('shipped', 'Shipped')
        DELIVERED = ('delivered', 'Delivered')
        CANCELLED = ('cancelled', 'Cancelled')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='orders')
    order_number = models.CharField(max_length=20, unique=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLACED, db_index=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    shipping = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Total delivery charge for the order (persisted at checkout).',
    )
    delivery_state_name = models.CharField(
        max_length=80,
        blank=True,
        default='',
        help_text='Snapshot of selected delivery state name at order time.',
    )
    gst_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    igst = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    coupon = models.ForeignKey(
        'Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    coupon_code = models.CharField(max_length=40, blank=True, default='')
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text='Coupon discount applied to merchandise (capped at subtotal).',
    )
    total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='orders')

    class Meta:
        ordering = ['-created_at']

    @property
    def total_delivery_charge(self):
        """Alias for shipping — order-level delivery total persisted at checkout."""
        return self.shipping

    @property
    def delivery_state(self):
        """Display name for selected delivery state (snapshot, then address FK/text)."""
        if self.delivery_state_name:
            return self.delivery_state_name
        addr = self.address
        if addr is None:
            return ''
        if addr.delivery_state_id and addr.delivery_state:
            return addr.delivery_state.name
        return addr.state or ''

    def __str__(self):
        return self.order_number


class OrderItem(TimeStampedModel):

    class LineKind(models.TextChoices):
        PURCHASE = ('purchase', 'Purchase')
        RENTAL = ('rental', 'Rental')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='order_items', null=True, blank=True)
    combo = models.ForeignKey(Combo, on_delete=models.PROTECT, related_name='order_items', null=True, blank=True)
    selected_variant = models.ForeignKey(Variant, on_delete=models.PROTECT, related_name='order_items', null=True, blank=True)
    product_name = models.CharField(max_length=200)
    variant_snapshot = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    line_type = models.CharField(max_length=16, choices=LineKind.choices, default=LineKind.PURCHASE, db_index=True)
    rental_key = models.CharField(max_length=40, blank=True, default='')
    rental_billing_period = models.CharField(max_length=8, blank=True)
    rental_period_count = models.PositiveIntegerField(null=True, blank=True)
    rental_snapshot = models.CharField(max_length=120, blank=True, help_text='Human-readable rental term for invoices.')
    rental_start_date = models.DateField(null=True, blank=True, db_index=True)
    rental_end_date = models.DateField(null=True, blank=True, db_index=True)
    hsn_code = models.CharField(max_length=20, blank=True, null=True)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    taxable_value = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Line taxable value (unit_price * qty) for GST lines.')
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='GST amount for this line.')
    is_gift = models.BooleanField(default=False, db_index=True)

    selected_pot_name = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text='Snapshot of pot product name at time of order.',
    )
    pot_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Snapshot of pot price at time of order.',
    )
    delivery_charge_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text='State delivery charge per pack at time of order.',
    )
    total_delivery_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text='per-pack charge × ceil(qty / DELIVERY_PACK_SIZE) (persisted).',
    )

    @property
    def line_total(self):
        pot_price = (self.pot_unit_price or 0) * self.quantity
        return (self.unit_price * self.quantity) + pot_price

    @property
    def line_grand_total(self):
        """Product line total plus this line's delivery charge."""
        return self.line_total + (self.total_delivery_charge or 0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(combo__isnull=False, product__isnull=True, selected_variant__isnull=True)
                    | models.Q(combo__isnull=True, product__isnull=False)
                ),
                name='orderitem_combo_xor_product',
            ),
        ]

    def __str__(self):
        return f'{self.order.order_number} - {self.product_name}'


class Payment(TimeStampedModel):

    class Method(models.TextChoices):
        COD = ('cod', 'Cash on Delivery')
        WHATSAPP = ('whatsapp', 'WhatsApp Order')
        RAZORPAY = ('razorpay', 'Online Payment')

    class Status(models.TextChoices):
        PENDING = ('pending', 'Pending')
        PAID = ('paid', 'Paid')
        FAILED = ('failed', 'Failed')
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.COD, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    processed_at = models.DateTimeField(blank=True, null=True)
    razorpay_order_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    def mark_paid(self):
        self.status = self.Status.PAID
        self.processed_at = timezone.now()
        self.save(update_fields=['status', 'processed_at'])


class Shipment(TimeStampedModel):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='shipment')
    shiprocket_order_id = models.CharField(max_length=100, blank=True, null=True)
    shiprocket_shipment_id = models.CharField(max_length=100, blank=True, null=True)
    awb_code = models.CharField(max_length=100, blank=True, null=True)
    courier_name = models.CharField(max_length=100, blank=True, null=True)
    label_url = models.URLField(blank=True, null=True)
    current_status = models.CharField(max_length=100, blank=True, null=True)
    tracking_data = models.JSONField(blank=True, null=True, default=dict)
    is_cancelled = models.BooleanField(default=False, db_index=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    error_log = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=['awb_code']), models.Index(fields=['shiprocket_order_id']), models.Index(fields=['shiprocket_shipment_id']), models.Index(fields=['is_cancelled'])]

    def __str__(self):
        return f'Shipment for {self.order.order_number}'


@receiver(post_save, sender=Order)
def auto_create_shipment_on_confirmed(sender, instance: Order, created: bool, update_fields=None, **kwargs):
    try:
        from app.delivery_utils import delivery_enabled
        if not delivery_enabled():
            return
        if instance.status != Order.Status.CONFIRMED:
            return
        if not created and update_fields is not None and ('status' not in update_fields):
            return
        if hasattr(instance, 'shipment'):
            return
        from app.services.shiprocket_service import create_shipment_for_order, ShiprocketAPIError
        shipment = Shipment.objects.create(order=instance, current_status='pending_creation')
        try:
            create_shipment_for_order(instance, shipment)
        except ShiprocketAPIError as exc:
            shipment.error_log = str(exc)
            shipment.current_status = 'error'
            shipment.save(update_fields=['error_log', 'current_status', 'updated_at'])
            logger.error('Shiprocket shipment creation failed for order %s: %s', instance.order_number, exc, exc_info=True)
        except Exception as exc:
            shipment.error_log = str(exc)
            shipment.current_status = 'error'
            shipment.save(update_fields=['error_log', 'current_status', 'updated_at'])
            logger.error('Unexpected error during shipment creation for order %s: %s', instance.order_number, exc, exc_info=True)
    except Exception as outer_exc:
        logger.error('auto_create_shipment_on_confirmed failed for order %s: %s', getattr(instance, 'order_number', None), outer_exc, exc_info=True)