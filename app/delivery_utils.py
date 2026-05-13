from django.conf import settings

def delivery_enabled() -> bool:
    return getattr(settings, 'DELIVERY_INTEGRATED', False)
