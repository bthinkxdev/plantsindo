from django.db import models

from .base import TimeStampedModel
from .product import Product


class ProductHighlight(TimeStampedModel):
    """
    One row = one PDP feature-highlight card (icon + short title + text).

    `text` is the original field (used as the card's description/body, and
    still consumed as a plain bullet by the "About this product" section).
    `title` and `icon` are additive — existing rows created before they
    existed just render with an empty title and the default fallback icon.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='highlights')
    title = models.CharField(max_length=120, blank=True, help_text='Short heading, e.g. "Perfect for".')
    text = models.CharField(max_length=400, help_text='Card body, e.g. "Home & Office".')
    icon = models.CharField(
        max_length=40,
        blank=True,
        help_text='Font Awesome solid icon name without the "fa-" prefix, e.g. "house", "wind", "gear", "seedling".',
    )
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True, help_text='Uncheck to hide without deleting.')

    class Meta:
        ordering = ['display_order', 'id']
        indexes = [models.Index(fields=['product', 'display_order'])]

    def __str__(self):
        return f'{self.product_id}: {self.text[:40]}'


class ProductWhatsInBoxItem(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='whats_in_box_items')
    label = models.CharField(max_length=200)
    detail = models.CharField(max_length=400, blank=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', 'id']
        indexes = [models.Index(fields=['product', 'display_order'])]

    def __str__(self):
        return f'{self.product_id}: {self.label}'


class ProductSpecification(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='specifications')
    name = models.CharField(max_length=120)
    value = models.CharField(max_length=500)
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', 'id']
        indexes = [models.Index(fields=['product', 'display_order'])]

    def __str__(self):
        return f'{self.name}: {self.value[:30]}'


class ProductContent(TimeStampedModel):
    """Long-form SEO / editorial body; one block per product."""
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='extended_content')
    title = models.CharField(max_length=200, blank=True, help_text='Optional heading above SEO body.')
    body = models.TextField(blank=True, help_text='Rich text / HTML for bottom-of-PDP SEO module.')

    class Meta:
        verbose_name_plural = 'Product content blocks'

    def __str__(self):
        return f'Content for {self.product_id}'
