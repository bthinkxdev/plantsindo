import hashlib
import secrets

from django.conf import settings
from django.db import models

from .base import TimeStampedModel
from .product import Variant


class ContactMessage(TimeStampedModel):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return f'{self.name} - {self.subject}'


class NewsletterSubscription(TimeStampedModel):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return self.email


class Wishlist(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist_items')
    selected_variant = models.ForeignKey(Variant, on_delete=models.CASCADE, null=True, blank=True, related_name='wishlisted_by')
    product = models.ForeignKey('Product', on_delete=models.CASCADE, null=True, blank=True, related_name='wishlisted_simple_by')

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'selected_variant'],
                condition=models.Q(selected_variant__isnull=False),
                name='unique_user_selected_variant_wishlist',
            ),
            models.UniqueConstraint(
                fields=['user', 'product'],
                condition=models.Q(product__isnull=False),
                name='unique_user_simple_product_wishlist',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(selected_variant__isnull=False, product__isnull=True)
                    | models.Q(selected_variant__isnull=True, product__isnull=False)
                ),
                name='wishlist_variant_xor_simple_product',
            ),
        ]
        indexes = [models.Index(fields=['user'])]

    def __str__(self):
        if self.selected_variant_id:
            return f'{self.user} — {self.selected_variant}'
        return f'{self.user} — {self.product}'


class UserProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        indexes = [models.Index(fields=['user'])]

    def __str__(self):
        return f'Profile: {self.user.email}'


class Banner(TimeStampedModel):
    MAX_ACTIVE = 5
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to='banners/')
    redirect_url = models.URLField(max_length=500, blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['display_order', 'created_at']
        indexes = [models.Index(fields=['is_active', 'display_order'])]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        active = Banner.objects.filter(is_active=True).order_by('display_order', 'created_at')
        if active.count() > self.MAX_ACTIVE:
            to_deactivate = active[self.MAX_ACTIVE:]
            Banner.objects.filter(pk__in=to_deactivate.values_list('pk', flat=True)).update(is_active=False)

    def __str__(self):
        return self.title or f'Banner #{self.pk}'


class OTPRequest(TimeStampedModel):
    email = models.EmailField(db_index=True)
    otp_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['email', 'is_used', 'expires_at']), models.Index(fields=['created_at', 'email'])]

    def __str__(self):
        return f"OTP for {self.email} - {('Used' if self.is_used else 'Active')}"

    @staticmethod
    def hash_otp(otp):
        return hashlib.sha256(str(otp).encode()).hexdigest()

    def verify_otp(self, otp):
        return self.otp_hash == self.hash_otp(otp)

    def is_valid(self):
        from django.utils import timezone
        return not self.is_used and timezone.now() < self.expires_at

    @classmethod
    def generate_otp(cls):
        return str(secrets.randbelow(10000)).zfill(4)
