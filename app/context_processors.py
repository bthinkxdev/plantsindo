from django.conf import settings
from django.core.cache import cache
from .models import CartItem, Wishlist, ContactMessage, Product
from .services import CartService
from .delivery_utils import delivery_enabled
from .wishlist_utils import (
    get_guest_wishlist_product_ids,
    get_guest_wishlist_variant_ids,
    guest_wishlist_total_count,
    wishlist_enabled,
)
from .services.category_tree import build_active_category_tree

def site_contact_context(request):
    instagram_handle = getattr(settings, 'SITE_INSTAGRAM', 'plantsindo.co')
    return {
        'site_phone': getattr(settings, 'SITE_PHONE', '+91 8848599575'),
        'site_whatsapp': getattr(settings, 'SITE_WHATSAPP', '918848599575'),
        'site_email': getattr(settings, 'SITE_EMAIL', 'hello@plantsindo.com'),
        'site_instagram': instagram_handle,
        'site_instagram_url': getattr(
            settings,
            'SITE_INSTAGRAM_URL',
            f'https://www.instagram.com/{instagram_handle}/',
        ),
        'site_facebook_url': getattr(
            settings,
            'SITE_FACEBOOK_URL',
            'https://www.facebook.com/profile.php?id=61589348505512',
        ),
    }

def cart_context(request):
    try:
        cart = CartService.get_or_create_cart(request)
        cart_count = sum((item.quantity for item in cart.items.all()))
        totals = CartService.compute_totals(cart)
        cart_subtotal = totals.subtotal
        cart_variant_ids = set()
        cart_simple_product_ids = set()
        for product_id, variant_id, line_type in cart.items.values_list('product_id', 'selected_variant_id', 'line_type'):
            if line_type != CartItem.LineKind.PURCHASE:
                continue
            if variant_id is not None:
                cart_variant_ids.add(variant_id)
            else:
                cart_simple_product_ids.add(product_id)
    except Exception:
        cart_count = 0
        cart_subtotal = 0
        cart_variant_ids = set()
        cart_simple_product_ids = set()
    return {'cart_count': cart_count, 'cart_subtotal': cart_subtotal, 'cart_variant_ids': cart_variant_ids, 'cart_simple_product_ids': cart_simple_product_ids}

def wishlist_context(request):
    enabled = wishlist_enabled()
    wishlist_variant_ids = []
    wishlist_product_ids = []
    wishlist_count = 0
    user = getattr(request, 'user', None)
    if not enabled:
        return {'wishlist_count': 0, 'wishlist_variant_ids': [], 'wishlist_product_ids': [], 'WISHLIST_ENABLED': False}
    if user and user.is_authenticated:
        wishlist_variant_ids = list(
            Wishlist.objects.filter(user=user, selected_variant__isnull=False)
            .filter(selected_variant__is_active=True, selected_variant__product__is_active=True)
            .values_list('selected_variant_id', flat=True)
        )
        wishlist_product_ids = list(
            Wishlist.objects.filter(user=user, product__isnull=False).filter(product__is_active=True).values_list('product_id', flat=True)
        )
        wishlist_count = Wishlist.objects.filter(user=user).count()
    else:
        wishlist_variant_ids = get_guest_wishlist_variant_ids(request)
        wishlist_product_ids = get_guest_wishlist_product_ids(request)
        wishlist_count = guest_wishlist_total_count(request)
    return {
        'wishlist_count': wishlist_count,
        'wishlist_variant_ids': wishlist_variant_ids,
        'wishlist_product_ids': wishlist_product_ids,
        'WISHLIST_ENABLED': enabled,
    }

def admin_message_badge(request):
    count = 0
    user = getattr(request, 'user', None)
    if user and user.is_authenticated and user.is_staff:
        count = ContactMessage.objects.filter(is_resolved=False).count()
    return {'admin_unresolved_messages': count}

def delivery_settings(request):
    return {
        'DELIVERY_INTEGRATED': delivery_enabled(),
        'DELIVERY_PACK_SIZE': int(getattr(settings, 'DELIVERY_PACK_SIZE', 2) or 2),
    }

def home_section_flags(request):
    return {'HOME_DEAL_OF_DAY_ENABLED': getattr(settings, 'HOME_DEAL_OF_DAY_ENABLED', True), 'HOME_FEATURED_ENABLED': getattr(settings, 'HOME_FEATURED_ENABLED', True), 'HOME_BESTSELLER_ENABLED': getattr(settings, 'HOME_BESTSELLER_ENABLED', True), 'HOME_RECENTLY_ADDED_ENABLED': getattr(settings, 'HOME_RECENTLY_ADDED_ENABLED', True), 'REVIEW_ENABLED': getattr(settings, 'REVIEW_ENABLED', True)}

def admin_product_settings(request):
    return {'ALLOW_ATTRIBUTES_AND_VARIANTS': getattr(settings, 'ALLOW_ATTRIBUTES_AND_VARIANTS', True)}

_RECENT_SEARCH_NAMES_CACHE_KEY = 'ctx:recent_product_search_names:v1'
_RECENT_SEARCH_NAMES_CACHE_TTL = 120


def get_recent_product_search_names(limit=10):
    """
    Active product names, newest first (by created_at), for storefront search placeholders.
    Cached briefly so list updates soon after new products are added.
    """
    if limit <= 0:
        return []
    cached = cache.get(_RECENT_SEARCH_NAMES_CACHE_KEY)
    if cached is not None:
        return list(cached)[:limit]
    names = list(
        Product.objects.filter(is_active=True)
        .order_by('-created_at')
        .values_list('name', flat=True)[:limit]
    )
    out = [str(n).strip() for n in names if str(n).strip()]
    cache.set(_RECENT_SEARCH_NAMES_CACHE_KEY, out, _RECENT_SEARCH_NAMES_CACHE_TTL)
    return out


def search_typed_suggestions(request):
    try:
        phrases = get_recent_product_search_names(limit=10)
    except Exception:
        phrases = []
    return {'search_typed_phrases': phrases}


def storefront_brand(request):
    tree = build_active_category_tree()
    root_ids = tree.children_ids.get(None, [])
    roots = [tree.by_id[cid] for cid in root_ids if cid in tree.by_id]
    roots.sort(key=lambda c: (c.name.lower(), c.pk))
    nav = roots[:16]
    nav_category_menu = []
    for parent in nav:
        child_ids = tree.children_ids.get(parent.pk, [])
        children = [tree.by_id[cid] for cid in child_ids if cid in tree.by_id]
        children.sort(key=lambda c: (c.name.lower(), c.pk))
        nav_category_menu.append({'parent': parent, 'children': children})
    return {
        'site_brand': getattr(settings, 'SITE_BRAND', 'Plantsindo'),
        'site_brand_part1': getattr(settings, 'SITE_BRAND_PART1', 'Plants'),
        'site_brand_part2': getattr(settings, 'SITE_BRAND_PART2', 'indo'),
        'site_tagline': getattr(settings, 'SITE_TAGLINE', 'Calm corners, lush leaves'),
        'nav_categories': nav,
        'nav_category_menu': nav_category_menu,
    }
