from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .base import TimeStampedModel
from .product import Product


class Review(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='reviews', null=True, blank=True)
    order = models.ForeignKey('Order', on_delete=models.SET_NULL, related_name='reviews', null=True, blank=True, help_text='The delivered order that verified this review.')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=200, blank=True)
    comment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True, db_index=True, help_text='Only approved reviews are shown on the storefront.')
    is_deleted = models.BooleanField(default=False, db_index=True, help_text='Soft delete flag; deleted reviews are hidden but kept for history.')

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['product', 'user'], name='unique_product_user_review'), models.CheckConstraint(condition=models.Q(rating__gte=1) & models.Q(rating__lte=5), name='review_rating_between_1_and_5')]
        indexes = [models.Index(fields=['product']), models.Index(fields=['rating']), models.Index(fields=['is_approved']), models.Index(fields=['product', 'is_approved'])]

    def __str__(self):
        uname = getattr(self.user, 'username', 'Anonymous')
        return f'Review for {self.product} by {uname} ({self.rating}★)'


ProductReview = Review


def _recompute_product_rating(product_id: int):
    if not product_id:
        return
    qs = Review.objects.filter(product_id=product_id, is_approved=True, is_deleted=False)
    agg = qs.aggregate(avg=Avg('rating'), cnt=Count('id'))
    avg = agg['avg'] or 0
    cnt = agg['cnt'] or 0
    Product.objects.filter(pk=product_id).update(average_rating=avg, total_reviews=cnt)


@receiver(post_save, sender=Review)
def review_post_save(sender, instance: Review, **kwargs):
    _recompute_product_rating(instance.product_id)


@receiver(post_delete, sender=Review)
def review_post_delete(sender, instance: Review, **kwargs):
    _recompute_product_rating(instance.product_id)
