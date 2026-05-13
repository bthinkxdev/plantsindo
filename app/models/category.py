import random
import string

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from .base import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children', db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True, help_text='Thumbnail / small tile; optional fallback if no shop banner is set.')
    banner_image = models.ImageField(upload_to='category_banners/', blank=True, null=True, help_text='Wide image for the shop page when this category is selected.')
    banner_tagline = models.CharField(max_length=200, blank=True, help_text='Optional short line over the banner (e.g. promotion text).')

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['is_active', 'name']), models.Index(fields=['parent', 'is_active', 'name'])]
        constraints = [models.CheckConstraint(condition=~models.Q(parent=models.F('id')), name='category_parent_not_self')]

    def clean(self):
        super().clean()
        if self.parent_id is None:
            return
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({'parent': 'A category cannot be its own parent.'})
        seen = set()
        cur = self.parent
        hops = 0
        while cur is not None:
            if cur.pk is None:
                break
            if cur.pk == self.pk:
                raise ValidationError({'parent': 'Circular category hierarchy is not allowed.'})
            if cur.pk in seen:
                raise ValidationError({'parent': 'Circular category hierarchy is not allowed.'})
            seen.add(cur.pk)
            cur = getattr(cur, 'parent', None)
            hops += 1
            if hops > 25:
                raise ValidationError({'parent': 'Category hierarchy is too deep.'})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = base_slug
            while Category.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                self.slug = f'{base_slug}-{random_suffix}'
        self.full_clean(exclude=['image', 'banner_image'])
        super().save(*args, **kwargs)

    def get_shop_banner_url(self):
        if self.banner_image:
            return self.banner_image.url
        if self.image:
            return self.image.url
        return None

    def get_full_path(self, separator=' > ', max_depth=10):
        parts = [self.name]
        seen = {self.pk} if self.pk else set()
        cur = self.parent
        depth = 0
        while cur is not None and depth < max_depth:
            if cur.pk and cur.pk in seen:
                break
            if cur.pk:
                seen.add(cur.pk)
            parts.append(cur.name)
            cur = getattr(cur, 'parent', None)
            depth += 1
        return separator.join(reversed(parts))

    def __str__(self):
        return self.name


class HomeCategory(TimeStampedModel):
    """
    Curated homepage tiles only — not part of the catalog Category tree.
    Optional linked_category ties the CTA to shop filtering without reusing Category display fields.
    """
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    banner_image = models.ImageField(upload_to='home_categories/', blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    link_url = models.URLField(max_length=500, blank=True, null=True, help_text='Optional. Full URL for the tile link; overrides shop category link when set.')
    linked_category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True, related_name='home_feature_links', help_text='Optional. When set (and link URL is empty), tile links to shop filtered by this category.')

    class Meta:
        ordering = ['display_order', 'name', 'id']
        indexes = [models.Index(fields=['display_order']), models.Index(fields=['is_active', 'display_order'])]

    def clean(self):
        super().clean()
        if self.link_url is not None and str(self.link_url).strip() == '':
            self.link_url = None

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            self.slug = base_slug
            while HomeCategory.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                self.slug = f'{base_slug}-{random_suffix}'
        self.full_clean(exclude=['banner_image'])
        return super().save(*args, **kwargs)

    def get_public_url(self) -> str:
        from django.urls import reverse
        if self.link_url:
            return str(self.link_url).strip()
        if self.linked_category_id and getattr(self, 'linked_category', None):
            return f"{reverse('store:product_list')}?category={self.linked_category.slug}"
        return reverse('store:product_list')

    def __str__(self):
        return self.name

    def curated_products_qs(self):
        from .product import Product
        return Product.objects.filter(home_category_links__home_category=self).order_by('home_category_links__display_order', 'home_category_links__id', 'id')


class HomeCategoryProduct(TimeStampedModel):
    """Curated products shown for a homepage category tile (ordered)."""
    home_category = models.ForeignKey(HomeCategory, on_delete=models.CASCADE, related_name='home_category_products')
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='home_category_links')
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', 'id']
        constraints = [models.UniqueConstraint(fields=['home_category', 'product'], name='uniq_home_category_product')]
        indexes = [models.Index(fields=['home_category', 'display_order'])]

    def __str__(self):
        return f'{self.home_category_id}:{self.product_id}'
