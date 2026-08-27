import logging
import random
import string
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .base import TimeStampedModel

logger = logging.getLogger(__name__)


class ProductQuerySet(models.QuerySet):

    def active(self):
        return self.filter(is_active=True)

    def available(self):
        from django.db.models import Q
        combo_ids = ProductComboItem.objects.values_list('combo_product_id', flat=True).distinct()
        return self.active().filter(Q(pk__in=combo_ids, is_combo_product=True) | Q(is_combo_product=False, variants__is_active=True, variants__stock_quantity__gt=0) | Q(is_combo_product=False, variants__isnull=True, base_stock__gt=0)).distinct()


class Product(TimeStampedModel):

    class Sunlight(models.TextChoices):
        FULL_SUN = ('full_sun', 'Full sun')
        PARTIAL = ('partial', 'Partial shade')
        LOW_LIGHT = ('low_light', 'Low light')

    class Watering(models.TextChoices):
        LOW = ('low', 'Low')
        MEDIUM = ('medium', 'Medium')
        HIGH = ('high', 'High')

    class Difficulty(models.TextChoices):
        EASY = ('easy', 'Easy')
        MEDIUM_DIF = ('medium', 'Medium')
        HARD = ('hard', 'Hard')

    class PlantType(models.TextChoices):
        INDOOR = ('indoor', 'Indoor')
        OUTDOOR = ('outdoor', 'Outdoor')
        FLOWERING = ('flowering', 'Flowering')
    category = models.ForeignKey('Category', on_delete=models.PROTECT, related_name='products')
    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    brand = models.CharField(max_length=120, blank=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_bestseller = models.BooleanField(default=False, db_index=True)
    is_deal_of_day = models.BooleanField(default=False, db_index=True)
    deal_of_day_start = models.DateField(blank=True, null=True, db_index=True)
    deal_of_day_end = models.DateField(blank=True, null=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0, help_text='Average star rating from verified reviews (1-5).')
    total_reviews = models.PositiveIntegerField(default=0, help_text='Total number of approved, non-deleted reviews.')
    is_gst_applicable = models.BooleanField(default=False, db_index=True)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text='GST %% (0-28). Required when is_gst_applicable is True.')
    hsn_code = models.CharField(max_length=20, blank=True, null=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    base_original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='MRP/Original price for simple products. Used for discount display.')
    base_stock = models.PositiveIntegerField(null=True, blank=True)
    sunlight = models.CharField(max_length=16, choices=Sunlight.choices, null=True, blank=True, db_index=True)
    watering = models.CharField(max_length=16, choices=Watering.choices, null=True, blank=True, db_index=True)
    difficulty = models.CharField(max_length=16, choices=Difficulty.choices, null=True, blank=True, db_index=True)
    plant_type = models.CharField(max_length=16, choices=PlantType.choices, null=True, blank=True, db_index=True)
    air_purifying = models.BooleanField(default=False, db_index=True)
    beginner_friendly = models.BooleanField(default=False, db_index=True)
    low_maintenance = models.BooleanField(default=False, db_index=True)
    office_friendly = models.BooleanField(default=False, db_index=True)
    is_plant_combo = models.BooleanField(default=False, db_index=True, help_text='Plant + pot / bundle offer')
    purchase_enabled = models.BooleanField(default=True, db_index=True, help_text='Allow add-to-cart as a purchase.')
    # Rental is configured via RentalConfig (app.models.rental.RentalConfig). Keep only a cheap flag here.
    is_rent_available = models.BooleanField(default=False, db_index=True, help_text='Expose rent option on storefront (details live in RentalConfig).')
    is_combo_product = models.BooleanField(default=False, db_index=True, help_text='Bundle: own price; stock follows simple component products.')
    is_legacy_combo = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Legacy Product row superseded by app.models.Combo; redirect storefront to Combo when set.',
    )
    care_instructions = models.TextField(blank=True, help_text='Care instructions (overview tab / plain text).')
    video_url = models.URLField(max_length=500, blank=True, help_text='Optional product video URL (e.g. YouTube embed or file).')
    germination_time_display = models.CharField(max_length=120, blank=True, help_text='Display label for germination time, e.g. 7–14 days.')
    harvest_time_display = models.CharField(max_length=120, blank=True)
    sowing_season_display = models.CharField(max_length=200, blank=True)
    maintenance_notes = models.TextField(blank=True, help_text='Maintenance tips (Care guide section).')
    is_giftable = models.BooleanField(default=True, db_index=True, help_text='Offer gift message / gift toggle on PDP when applicable.')
    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['is_active', 'is_featured']), models.Index(fields=['is_active', 'is_bestseller']), models.Index(fields=['is_active', 'is_deal_of_day']), models.Index(fields=['category', 'is_active']), models.Index(fields=['is_active', 'brand']), models.Index(fields=['is_active', 'beginner_friendly']), models.Index(fields=['is_active', 'difficulty', 'sunlight'])]

    @property
    def has_rent_option(self) -> bool:
        return bool(self.is_rent_available)

    def clean(self):
        super().clean()
        if not self.purchase_enabled and not self.is_rent_available:
            raise ValidationError('Enable at least one of purchase or rent availability.')
        if self.is_combo_product and self.pk and self.variants.exists():
            raise ValidationError({'is_combo_product': 'Combo products must not have variants — use simple listing with component lines only.'})
        if self.is_combo_product and self.pk and self.combo_components.exists():
            from app.services.rental_catalog import assert_combo_children_allowed
            assert_combo_children_allowed(self)
        if self.is_gst_applicable:
            if self.gst_percentage is None:
                raise ValidationError({'gst_percentage': 'GST %% is required when GST is applicable.'})
            try:
                pct = Decimal(str(self.gst_percentage))
                if pct < 0 or pct > 28:
                    raise ValidationError({'gst_percentage': 'GST %% must be between 0 and 28.'})
            except (TypeError, ValueError):
                raise ValidationError({'gst_percentage': 'Enter a valid GST percentage.'})
        elif self.gst_percentage is not None:
            raise ValidationError({'gst_percentage': 'Clear GST %% when GST is not applicable.'})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = base_slug
            while Product.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                self.slug = f'{base_slug}-{random_suffix}'
        super().save(*args, **kwargs)

    def _normalize_card_image_url(self, url):
        if not url or not isinstance(url, str):
            return url
        url = url.strip()
        if url.startswith('http://') or url.startswith('https://'):
            return url
        if url.startswith('/'):
            base = getattr(settings, 'MEDIA_URL', '/media/').rstrip('/')
            if base and '/media/' in url and ('ytimg.com' in url) and url.startswith(base + '/'):
                return 'https://' + url[len(base) + 1:]
            return url
        return 'https://' + url.lstrip('/')

    @property
    def discount_percent(self):
        if not self.base_original_price or not self.base_price:
            return 0
        if self.base_original_price <= self.base_price:
            return 0
        try:
            discount = (self.base_original_price - self.base_price) / self.base_original_price * 100
            return round(discount)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0

    def has_any_sellable_stock(self):
        if getattr(self, '_has_sellable_stock', None) is not None:
            return self._has_sellable_stock
        if getattr(self, 'is_combo_product', False):
            from app.services.rental_catalog import combo_is_in_stock
            self._has_sellable_stock = combo_is_in_stock(self, multiplier=1)
            return self._has_sellable_stock
        if self.variants.exists():
            for v in self.variants.all():
                if getattr(v, 'is_active', True) and (getattr(v, 'stock_quantity', 0) or 0) > 0:
                    self._has_sellable_stock = True
                    return True
            self._has_sellable_stock = False
            return False
        stock = getattr(self, 'base_stock', None)
        self._has_sellable_stock = bool(stock and stock > 0)
        return self._has_sellable_stock

    def has_variants(self):
        return self.variants.exists()

    def is_simple_product(self):
        return not self.has_variants()

    def get_price(self):
        if self.has_variants():
            v = self.variants.filter(is_active=True).order_by('price').only('price').first()
            return v.price if v else None
        return self.base_price

    def get_stock(self):
        if self.has_variants():
            return sum((v.stock_quantity or 0 for v in self.variants.filter(is_active=True).only('stock_quantity')))
        return self.base_stock or 0

    def get_card_image_urls(self, limit=20):
        urls = []
        seen = set()
        try:
            if self.variants.exists():
                for v in self.variants.filter(is_active=True).order_by('display_order', 'id'):
                    if len(urls) >= limit:
                        break
                    for img in v.images.filter(image__isnull=False).exclude(image='').order_by('-is_primary', 'display_order', 'id')[:1]:
                        if img.image:
                            url = img.image.url
                            if url:
                                url = self._normalize_card_image_url(url)
                            if url and url not in seen:
                                seen.add(url)
                                urls.append(url)
                                break
            else:
                for img in self.images.filter(image__isnull=False).exclude(image='').order_by('-is_primary', 'display_order', 'id')[:limit]:
                    if img.image:
                        url = img.image.url
                        if url:
                            url = self._normalize_card_image_url(url)
                        if url and url not in seen:
                            seen.add(url)
                            urls.append(url)
        except Exception:
            pass
        return urls[:limit] if urls else []

    @property
    def is_recent_launch(self):
        if not self.pk or not self.created_at:
            return False
        return (timezone.now() - self.created_at).days <= 21

    def __str__(self):
        return self.name


class ProductComboItem(TimeStampedModel):
    """Maps a combo parent product to simple component products (with quantities)."""
    combo_product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='combo_components')
    component_product = models.ForeignKey('Product', on_delete=models.PROTECT, related_name='combo_memberships')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', 'id']
        constraints = [models.UniqueConstraint(fields=['combo_product', 'component_product'], name='uniq_combo_component')]
        indexes = [models.Index(fields=['combo_product', 'display_order'])]

    def __str__(self):
        return f'{self.combo_product_id} → {self.component_product_id} × {self.quantity}'


class ProductAttribute(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='attributes')
    name = models.CharField(max_length=120)
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', 'name', 'id']
        constraints = [models.UniqueConstraint(fields=['product', 'name'], name='unique_product_attribute_name')]
        indexes = [models.Index(fields=['product', 'display_order'])]

    def __str__(self):
        return f'{self.product.name} — {self.name}'


class ProductAttributeValue(TimeStampedModel):
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=200)
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', 'value', 'id']
        constraints = [models.UniqueConstraint(fields=['attribute', 'value'], name='unique_attribute_value')]
        indexes = [models.Index(fields=['attribute', 'display_order'])]

    def __str__(self):
        return f'{self.attribute.name}: {self.value}'


class Variant(TimeStampedModel):

    class PotSize(models.TextChoices):
        SMALL = ('small', 'Small')
        MEDIUM = ('medium', 'Medium')
        LARGE = ('large', 'Large')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    attribute_values = models.ManyToManyField(ProductAttributeValue, related_name='variants', through='VariantAttributeValue', blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='MRP/Original price for discount display on this variant.')
    stock_quantity = models.PositiveIntegerField(default=0)
    weight = models.DecimalField(max_digits=6, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    length = models.DecimalField(max_digits=6, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    breadth = models.DecimalField(max_digits=6, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    height = models.DecimalField(max_digits=6, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    sku = models.CharField(max_length=64, unique=True, blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    pot_size = models.CharField(max_length=16, choices=PotSize.choices, blank=True, db_index=True)
    plant_height_display = models.CharField(max_length=32, blank=True, help_text='Display height label, e.g. "1 ft", "2 ft".')
    includes_pot = models.BooleanField(null=True, blank=True, help_text='With pot / without pot when applicable.')

    class Meta:
        ordering = ['display_order', 'id']
        constraints = [models.CheckConstraint(condition=models.Q(stock_quantity__gte=0), name='variant_stock_non_negative'), models.CheckConstraint(condition=models.Q(price__gte=0), name='variant_price_non_negative')]
        indexes = [models.Index(fields=['product', 'is_active', 'stock_quantity'])]

    def get_attribute_values_display(self):
        values = list(self.attribute_values.select_related('attribute').order_by('attribute__display_order', 'display_order'))
        return ' / '.join((av.value for av in values)) if values else ''

    def __str__(self):
        display = self.get_attribute_values_display()
        return f'{self.product.name} — {display}' if display else f'{self.product.name} (variant #{self.pk})'

    @property
    def discount_percent(self):
        if not self.original_price or not self.price:
            return 0
        if self.original_price <= self.price:
            return 0
        try:
            discount = (self.original_price - self.price) / self.original_price * 100
            return round(discount)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0


class VariantAttributeValue(TimeStampedModel):
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name='variant_attr_values')
    attribute_value = models.ForeignKey(ProductAttributeValue, on_delete=models.CASCADE, related_name='variant_attr_values')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['variant', 'attribute_value'], name='unique_variant_attribute_value')]


class VariantImage(TimeStampedModel):
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/variant_images/')
    is_primary = models.BooleanField(default=False, db_index=True)
    alt_text = models.CharField(max_length=200, blank=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', '-is_primary', 'id']
        indexes = [models.Index(fields=['variant', 'is_primary']), models.Index(fields=['variant', 'display_order'])]

    def __str__(self):
        return f'{self.variant} image'


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/base_images/')
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', '-is_primary', 'id']
        indexes = [models.Index(fields=['product', 'display_order'])]

    def __str__(self):
        return f'{self.product} base image'

class ProductPotAddon(TimeStampedModel):
    """
    Links a plant product to pot products that customers can optionally add.
    Pots are regular Product objects under a category whose slug is 'pot' or 'pots'.
    Both products remain independently sellable.
    """
    plant_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='pot_addons',
        help_text='The plant product this addon belongs to.',
    )
    pot_product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='linked_as_pot_addon',
        help_text='The pot product available as an add-on.',
    )
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['plant_product', 'pot_product'],
                name='uniq_plant_pot_addon',
            )
        ]
        indexes = [
            models.Index(fields=['plant_product', 'display_order']),
        ]

    def __str__(self):
        return f'{self.plant_product.name} → {self.pot_product.name}'