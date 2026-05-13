from django.conf import settings

GUEST_WISHLIST_SESSION_KEY = 'wishlist'
GUEST_WISHLIST_PRODUCTS_KEY = 'wishlist_products'
GUEST_WISHLIST_MAX_ITEMS = 50


def wishlist_enabled() -> bool:
    return getattr(settings, 'WISHLIST_ENABLED', True)


def _normalize_positive_int_ids(raw):
    out = []
    seen = set()
    for x in raw or []:
        try:
            i = int(x)
            if 0 < i and i not in seen:
                seen.add(i)
                out.append(i)
        except (TypeError, ValueError):
            continue
    return out[:GUEST_WISHLIST_MAX_ITEMS]


def get_guest_wishlist_variant_ids(request):
    return _normalize_positive_int_ids(request.session.get(GUEST_WISHLIST_SESSION_KEY))


def set_guest_wishlist_variant_ids(request, ids):
    request.session[GUEST_WISHLIST_SESSION_KEY] = _normalize_positive_int_ids(ids)
    request.session.modified = True


def get_guest_wishlist_product_ids(request):
    return _normalize_positive_int_ids(request.session.get(GUEST_WISHLIST_PRODUCTS_KEY))


def set_guest_wishlist_product_ids(request, ids):
    request.session[GUEST_WISHLIST_PRODUCTS_KEY] = _normalize_positive_int_ids(ids)
    request.session.modified = True


def guest_wishlist_total_count(request):
    return len(get_guest_wishlist_variant_ids(request)) + len(get_guest_wishlist_product_ids(request))


def guest_wishlist_room_left(request):
    return max(0, GUEST_WISHLIST_MAX_ITEMS - guest_wishlist_total_count(request))
