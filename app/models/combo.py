import random
import string
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify

from .base import TimeStampedModel
from .product import Product


class Combo(TimeStampedModel):
    """Sellable bundle: owns storefront identity, price, and copy; links to component products."""

    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(max_length=220, unique=True, db_index=True)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True, help_text='Bundle instructions (delivery, inclusions, etc.)')
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to='combos/', blank=True, null=True, help_text='Optional cover image for cards / cart.')
    is_active = models.BooleanField(default=True, db_index=True)
    show_in_combos_nav = models.BooleanField(default=False, db_index=True, help_text='When True, listed on Shop → Combos.')
    purchase_enabled = models.BooleanField(default=True, db_index=True)
    is_gst_applicable = models.BooleanField(default=False, db_index=True)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    hsn_code = models.CharField(max_length=20, blank=True, null=True)
    # Set when this combo was migrated from a legacy Product-based bundle (slug redirect).
    legacy_product = models.OneToOneField(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replaced_by_combo',
    )

    class Meta:
        ordering = ('-updated_at', '-created_at')
        indexes = [
            models.Index(fields=('is_active', 'show_in_combos_nav')),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or 'combo'
            self.slug = base
            while Combo.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base}-{"".join(random.choices(string.ascii_lowercase + string.digits, k=4))}'
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.is_gst_applicable:
            if self.gst_percentage is None:
                raise ValidationError({'gst_percentage': 'GST % is required when GST is applicable.'})
            pct = Decimal(str(self.gst_percentage))
            if pct < 0 or pct > 28:
                raise ValidationError({'gst_percentage': 'GST % must be between 0 and 28.'})
        elif self.gst_percentage is not None:
            raise ValidationError({'gst_percentage': 'Clear GST % when GST is not applicable.'})
        if self.original_price is not None and self.price is not None and self.original_price <= self.price:
            raise ValidationError({'original_price': 'Original price must be greater than selling price when set.'})
        if self.original_price and (not self.price or self.price <= 0):
            raise ValidationError({'price': 'Selling price is required when original price is set.'})

    @property
    def discount_percent(self) -> int:
        if not self.original_price or not self.price:
            return 0
        if self.original_price <= self.price:
            return 0
        try:
            return int(round((self.original_price - self.price) / self.original_price * 100))
        except (TypeError, ZeroDivisionError):
            return 0


class ComboItem(TimeStampedModel):
    combo = models.ForeignKey(Combo, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='combo_memberships_v2')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ('display_order', 'id')
        constraints = [
            models.UniqueConstraint(fields=('combo', 'product'), name='uniq_comboitem_combo_product'),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name='comboitem_qty_positive'),
        ]
        indexes = [models.Index(fields=('combo', 'display_order'))]

    def __str__(self):
        return f'{self.combo_id} → {self.product_id} × {self.quantity}'
