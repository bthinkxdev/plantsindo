import logging
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from .models import Banner, Category, VariantImage
logger = logging.getLogger(__name__)

def _delete_image_file(image_field):
    if not image_field or not image_field.name:
        return
    try:
        storage = image_field.storage
        name = image_field.name
        logger.info(f'Deleting old image from storage: {name}')
        storage.delete(name)
    except Exception as e:
        logger.warning(f"Failed to delete image file '{image_field.name}': {e}")

@receiver(post_delete, sender=Category)
def delete_category_image_file(sender, instance, **kwargs):
    _delete_image_file(instance.image)

@receiver(pre_save, sender=Category)
def delete_old_category_image_on_update(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_image = Category.objects.get(pk=instance.pk).image
    except Category.DoesNotExist:
        return
    if old_image and old_image != instance.image:
        _delete_image_file(old_image)

@receiver(post_delete, sender=VariantImage)
def delete_variant_image_file(sender, instance, **kwargs):
    _delete_image_file(instance.image)

@receiver(pre_save, sender=VariantImage)
def delete_old_variant_image_on_update(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_image = VariantImage.objects.get(pk=instance.pk).image
    except VariantImage.DoesNotExist:
        return
    if old_image and old_image != instance.image:
        _delete_image_file(old_image)

@receiver(post_delete, sender=Banner)
def delete_banner_image_file(sender, instance, **kwargs):
    _delete_image_file(instance.image)

@receiver(pre_save, sender=Banner)
def delete_old_banner_image_on_update(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_image = Banner.objects.get(pk=instance.pk).image
    except Banner.DoesNotExist:
        return
    if old_image and old_image != instance.image:
        _delete_image_file(old_image)
