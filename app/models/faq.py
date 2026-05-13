from django.db import models

from .base import TimeStampedModel
from .product import Product


class ProductFAQ(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='faqs')
    question = models.CharField(max_length=300)
    answer = models.TextField()
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', 'id']
        verbose_name = 'Product FAQ'
        verbose_name_plural = 'Product FAQs'
        indexes = [models.Index(fields=['product', 'display_order'])]

    def __str__(self):
        return self.question[:60]
