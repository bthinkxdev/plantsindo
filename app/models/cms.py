from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.text import slugify

from .base import TimeStampedModel


class BlogPost(TimeStampedModel):
    title = models.CharField(max_length=220, db_index=True)
    slug = models.SlugField(max_length=240, unique=True, db_index=True)
    excerpt = models.CharField(max_length=500, blank=True)
    body = models.TextField(help_text='Plain text or HTML, depending on storefront rendering.')
    cover_image = models.ImageField(upload_to='blog/covers/', blank=True, null=True)
    is_published = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ('-published_at', '-created_at')
        verbose_name = 'blog post'
        verbose_name_plural = 'blog posts'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            base = slugify(self.title)[:200] or 'post'
            slug = base
            n = 1
            while BlogPost.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f'{base}-{n}'
            self.slug = slug
        super().save(*args, **kwargs)


class Reel(TimeStampedModel):
    title = models.CharField(max_length=200)
    caption = models.CharField(max_length=500, blank=True)
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='reels', null=True, blank=True)
    video = models.FileField(
        upload_to='reels/videos/',
        validators=[FileExtensionValidator(allowed_extensions=('mp4', 'webm', 'mov'))],
        help_text='Short vertical video (e.g. mp4, webm, mov).',
    )
    poster_image = models.ImageField(upload_to='reels/posters/', blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ('display_order', '-created_at')
        verbose_name = 'reel'
        verbose_name_plural = 'reels'

    def __str__(self):
        return self.title or f'Reel #{self.pk}'
    
class Testimonial(TimeStampedModel):
    """
    Customer testimonial shown on the storefront homepage.
    Managed entirely from the admin dashboard (no customer-side submission).
    """
 
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]   # 1 – 5 stars
 
    name          = models.CharField(max_length=120)
    photo         = models.ImageField(
                        upload_to='testimonials/',
                        blank=True,
                        null=True,
                        help_text='Square portrait recommended (min 200 × 200 px).',
                    )
    rating        = models.PositiveSmallIntegerField(
                        choices=RATING_CHOICES,
                        default=5,
                        db_index=True,
                    )
    description   = models.TextField(help_text='The review / testimonial text.')
    is_verified   = models.BooleanField(
                        default=True,
                        help_text='Shows a "Verified Buyer" badge on the storefront.',
                    )
    is_active     = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(
                        default=0,
                        db_index=True,
                        help_text='Lower numbers appear first.',
                    )
 
    class Meta:
        ordering = ['display_order', '-created_at']
        indexes  = [models.Index(fields=['is_active', 'display_order'])]
        verbose_name        = 'testimonial'
        verbose_name_plural = 'testimonials'
 
    def __str__(self):
        return f'{self.name} — {self.rating}★'
