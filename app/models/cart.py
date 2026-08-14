from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .base import TimeStampedModel
from .combo import Combo
from .product import Product, Variant


class Cart(TimeStampedModel):

    class Status(models.TextChoices):
        ACTIVE = ('active', 'Active')
        ORDERED = ('ordered', 'Ordered')
        ABANDONED = ('abandoned', 'Abandoned')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, blank=True, null=True, related_name='carts')
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'status']), models.Index(fields=['session_key', 'status'])]

    def __str__(self):
        return f'Cart {self.pk} ({self.status})'

    @property
    def subtotal(self):
        return sum((item.line_total for item in self.items.select_related('product', 'combo')))

    def _get_gst_aggregates(self):
        from decimal import Decimal
        taxable = Decimal('0')
        non_taxable = Decimal('0')
        gst_total = Decimal('0')
        for item in self.items.select_related('product', 'combo'):
            line = item.line_total
            if item.combo_id:
                c = item.combo
                if getattr(c, 'is_gst_applicable', False) and getattr(c, 'gst_percentage', None) is not None:
                    taxable += line
                    pct = c.gst_percentage
                    gst_total += line * (pct / Decimal('100'))
                else:
                    non_taxable += line
            elif getattr(item.product, 'is_gst_applicable', False) and getattr(item.product, 'gst_percentage', None) is not None:
                taxable += line
                pct = item.product.gst_percentage
                gst_total += line * (pct / Decimal('100'))
            else:
                non_taxable += line
        return (taxable, non_taxable, gst_total)

    @property
    def taxable_total(self):
        return self._get_gst_aggregates()[0]

    @property
    def non_taxable_total(self):
        return self._get_gst_aggregates()[1]

    @property
    def gst_total(self):
        return self._get_gst_aggregates()[2]

    @property
    def grand_total(self):
        return self.subtotal + self.gst_total


class CartItem(TimeStampedModel):

    class LineKind(models.TextChoices):
        PURCHASE = ('purchase', 'Purchase')
        RENTAL = ('rental', 'Rental')
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='cart_items', null=True, blank=True)
    combo = models.ForeignKey(Combo, on_delete=models.PROTECT, related_name='cart_items', null=True, blank=True)
    selected_variant = models.ForeignKey(Variant, on_delete=models.PROTECT, related_name='cart_items', null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    line_type = models.CharField(max_length=16, choices=LineKind.choices, default=LineKind.PURCHASE, db_index=True)
    rental_key = models.CharField(max_length=40, blank=True, default='', db_index=True, help_text='Empty for purchase; e.g. week:2 for rental identity.')
    rental_billing_period = models.CharField(max_length=8, blank=True, help_text='day, week, or month when line_type is rental.')
    rental_period_count = models.PositiveIntegerField(null=True, blank=True, help_text='Number of billing periods for this rental line.')
    rental_start_date = models.DateField(null=True, blank=True, db_index=True)
    rental_end_date = models.DateField(null=True, blank=True, db_index=True)
    is_gift = models.BooleanField(default=False, db_index=True, help_text='Gift wrap / gift order flag for this line.')

    # ── Pot add-on (optional) ──────────────────────────────────────────────────
    selected_pot = models.ForeignKey(
        'Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cart_items_as_pot',
        help_text='Optional pot product added alongside this plant.',
    )
    pot_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Snapshot of pot price at time of adding to cart.',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'selected_variant', 'line_type', 'rental_key', 'is_gift', 'selected_pot'],
                name='uniq_cart_variant_line',
                condition=models.Q(selected_variant__isnull=False),
            ),
            models.UniqueConstraint(
                fields=['cart', 'product', 'line_type', 'rental_key', 'is_gift', 'selected_pot'],
                name='uniq_cart_simple_line',
                condition=models.Q(selected_variant__isnull=True, combo__isnull=True),
            ),
            models.UniqueConstraint(
                fields=['cart', 'combo', 'line_type', 'rental_key', 'is_gift'],
                name='uniq_cart_combo_line',
                condition=models.Q(combo__isnull=False),
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(combo__isnull=False, product__isnull=True, selected_variant__isnull=True)
                    | models.Q(combo__isnull=True, product__isnull=False)
                ),
                name='cartitem_combo_xor_product',
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name='cartitem_qty_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['cart', 'product']),
            models.Index(fields=['cart', 'line_type']),
            models.Index(fields=['cart', 'combo']),
        ]
    def rental_label(self) -> str:
        if self.line_type != self.LineKind.RENTAL or not self.rental_billing_period or not self.rental_period_count:
            return ''
        if self.rental_start_date and self.rental_end_date:
            return f'{self.rental_start_date.strftime("%d %b")} → {self.rental_end_date.strftime("%d %b")}'
        b = self.rental_billing_period
        n = self.rental_period_count
        if b == 'day':
            return f'{n} day' + ('s' if n != 1 else '')
        if b == 'week':
            return f'{n} week' + ('s' if n != 1 else '')
        if b == 'month':
            return f'{n} month' + ('s' if n != 1 else '')
        return self.rental_key or 'Rental'

    @property
    def variant_display(self):
        if self.combo_id:
            return 'Bundle'
        if self.selected_variant_id and self.selected_variant:
            base = self.selected_variant.get_attribute_values_display()
        else:
            base = ''
        if self.line_type == self.LineKind.RENTAL:
            lbl = self.rental_label()
            if lbl:
                base = f'{base} · Rent: {lbl}' if base else f'Rent: {lbl}'
        if self.selected_pot_id and self.selected_pot:
            pot_label = f'+ {self.selected_pot.name}'
            base = f'{base} · {pot_label}' if base else pot_label
        return base

    @property
    def line_total(self):
        pot_price = (self.pot_unit_price or 0) * self.quantity
        return (self.unit_price * self.quantity) + pot_price

    @property
    def pot_line_total(self):
        """Just the pot portion of this line."""
        if not self.selected_pot_id or not self.pot_unit_price:
            return 0
        return self.pot_unit_price * self.quantity

    def get_display_image_url(self):
        if self.combo_id and self.combo:
            try:
                if self.combo.image and self.combo.image.name:
                    return self.combo.image.url
            except Exception:
                pass
            try:
                row = self.combo.items.select_related('product').first()
                if row and row.product_id:
                    urls = row.product.get_card_image_urls(limit=1)
                    return urls[0] if urls else None
            except Exception:
                pass
            return None
        if self.selected_variant_id:
            for img in self.selected_variant.images.filter(image__isnull=False).exclude(image='').order_by('-is_primary', 'display_order', 'id')[:1]:
                try:
                    if img.image:
                        return img.image.url
                except Exception:
                    pass
            return None
        if self.product_id:
            urls = self.product.get_card_image_urls(limit=1)
            return urls[0] if urls else None
        return None

    @property
    def catalog_name(self) -> str:
        if self.combo_id and self.combo:
            return self.combo.name
        if self.product_id and self.product:
            return self.product.name
        return ''

    def __str__(self):
        kind = 'rent' if self.line_type == self.LineKind.RENTAL else 'buy'
        gift = ' gift' if self.is_gift else ''
        name = self.catalog_name or 'Item'
        return f'{name} ({kind}){gift} x {self.quantity}'

    @property
    def max_allowed_quantity(self):
        from django.conf import settings
        max_cart = getattr(settings, 'MAX_CART_QTY', 10)
        
        if self.selected_variant:
            stock = self.selected_variant.stock_quantity if self.selected_variant.stock_quantity is not None else 99
        elif self.product:
            stock = self.product.base_stock if self.product.base_stock is not None else 99
        elif self.combo:
            stock = getattr(self.combo, 'stock', 99)
        else:
            stock = 99
            
        return min(stock, max_cart)

    @property
    def actual_stock(self):
        if self.selected_variant:
            return self.selected_variant.stock_quantity if self.selected_variant.stock_quantity is not None else 99
        elif self.product:
            return self.product.base_stock if self.product.base_stock is not None else 99
        elif self.combo:
            return getattr(self.combo, 'stock', 99)
        return 99
