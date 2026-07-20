from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q, F, Sum, Count, Min
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import DetailView, FormView, ListView, TemplateView, View
from django.utils import timezone
from .captcha import CaptchaError, captcha_required, extract_captcha_token, verify_captcha
from .auth_views import get_client_ip
import json
import razorpay
import hmac
import hashlib
import logging
logger = logging.getLogger(__name__)
from .auth_decorators import LoginRequiredForActionMixin
from .forms import CartAddForm, CartUpdateForm, CheckoutForm, ContactForm, NewsletterForm, ReviewForm
from .models import Banner, CartItem, Category, Combo, ComboItem, HomeCategory, HomeCategoryProduct, Order, OrderItem, Payment, Product, ProductComboItem, Reel, Review, Variant, Cart, Wishlist, Shipment, Testimonial
from .services import CartError, CartService, OrderService, StockError, send_order_confirmation_email_async
from .services.cart_order import (
    format_cart_delivery_error,
    format_cart_stock_error,
    get_cart_delivery_issues,
    get_cart_stock_issues,
    resolve_checkout_totals,
)
from .services.state_delivery_service import resolve_delivery_state_id
from .services.product_service import ProductDetailService, get_pdp_queryset
from .services.catalog import active_variant_qs, apply_plant_filters_to_product_qs, apply_plant_filters_to_variant_qs, collection_card_items, collection_combo_cards
from .services.category_tree import build_active_category_tree, category_filter_ids_for_slug
from .wishlist_utils import (
    get_guest_wishlist_product_ids,
    get_guest_wishlist_variant_ids,
    guest_wishlist_room_left,
    guest_wishlist_total_count,
    set_guest_wishlist_product_ids,
    set_guest_wishlist_variant_ids,
    wishlist_enabled,
)
from django.core.cache import caches

try:
    _cache = caches['locmem']
except Exception:
    _cache = caches['default']

_HOME_CACHE_TTL = getattr(settings, 'HOME_CACHE_TTL', 120)
_SHOP_CACHE_TTL = getattr(settings, 'SHOP_CACHE_TTL', 60)


def _build_product_cards(products_iterable, limit: int):
    """
    Given an iterable of Product objects (already fetched), attach
    primary_variant / lowest_price and return up to `limit` cards.
    Pure Python — no extra DB queries.
    """
    cards = []
    for product in products_iterable:
        if len(cards) >= limit:
            break
        variants = list(getattr(product, 'sellable_variants', []) or [])
        if variants:
            primary_variant = min(variants, key=lambda v: (v.price, v.display_order, v.id))
            product.primary_variant = primary_variant
            product.lowest_price = primary_variant.price
            cards.append(product)
        elif getattr(product, 'is_combo_product', False):
            from .services.rental_catalog import combo_is_in_stock
            if combo_is_in_stock(product, multiplier=1) and product.base_price is not None:
                product.primary_variant = None
                product.lowest_price = product.base_price
                cards.append(product)
        elif getattr(product, 'base_stock', 0) and product.base_stock > 0:
            product.primary_variant = None
            product.lowest_price = product.base_price
            cards.append(product)
    return cards
 
 
# ──────────────────────────────────────────────────────────────
# HOME PAGE — cached product data loader
# ──────────────────────────────────────────────────────────────
 
def _load_home_product_data():
    """
    All expensive product queries for the home page in a SINGLE pass.
 
    BEFORE: 7 separate Product.objects.available() calls (deals, bestsellers,
            new arrivals, top_rated, budget, featured, beginner).
    AFTER:  ONE queryset fetching up to 200 available products with all needed
            prefetches. Python then splits them into sections — zero extra DB hits.
 
    Also fixes the home_category N+1: all HomeCategoryProduct rows are fetched
    in one query, product PKs batched, then one Product queryset for all of them.
 
    Result: ~3 DB queries total for the entire product data layer (was 15+).
    Cached for HOME_CACHE_TTL seconds (default 120 s).
    """
    CACHE_KEY = 'home_product_data_v1'
    cached = _cache.get(CACHE_KEY)
    if cached is not None:
        return cached
 
    # ── Shared variant prefetch ──
    sellable_variants_qs = (
        Variant.objects.filter(is_active=True, stock_quantity__gt=0)
        .prefetch_related('images')
        .order_by('display_order', 'id')
    )
    variant_pf = Prefetch('variants', queryset=sellable_variants_qs, to_attr='sellable_variants')
 
    # ── ONE master product fetch ──
    # Fetch 200 products ordered newest-first; Python handles all section splits.
    all_products = list(
        Product.objects.available()
        .select_related('category', 'rental_config')
        .prefetch_related(variant_pf)
        .order_by('-created_at')[:200]
    )
 
    today = timezone.now().date()
 
    # Split into section buckets in Python — zero extra queries
    deals_raw       = [p for p in all_products if p.is_deal_of_day
                       and (not p.deal_of_day_start or p.deal_of_day_start <= today)
                       and (not p.deal_of_day_end   or p.deal_of_day_end   >= today)]
    bestsellers_raw = [p for p in all_products if p.is_bestseller]
    featured_raw    = [p for p in all_products if p.is_featured]
    beginner_raw    = [p for p in all_products if p.beginner_friendly]
 
    # Top-rated needs rating filter — small slice from master list
    top_rated_raw   = sorted(
        [p for p in all_products if (p.average_rating or 0) >= 4 and (p.total_reviews or 0) > 0],
        key=lambda p: (-float(p.average_rating or 0), -(p.total_reviews or 0))
    )
 
    # Budget: needs price filter — use master list, re-filter in Python
    budget_raw = sorted(
        [p for p in all_products if _cheapest_price(p) is not None and _cheapest_price(p) <= 499],
        key=lambda p: _cheapest_price(p)
    )
 
    # New arrivals = all_products (already ordered by -created_at)
    new_arrivals_raw = all_products
 
    # Build cards
    deal_cards      = _build_product_cards(deals_raw,       8)
    bestseller_cards = _build_product_cards(bestsellers_raw, 8)
    featured_cards  = _build_product_cards(featured_raw,    8)
    beginner_cards  = _build_product_cards(beginner_raw,    8)
    top_rated_cards = _build_product_cards(top_rated_raw,   8)
    budget_cards    = _build_product_cards(budget_raw,      8)
    new_arrival_cards = _build_product_cards(new_arrivals_raw, 26)
 
    # Fallbacks (same logic as original)
    if not deal_cards and getattr(settings, 'HOME_DEAL_OF_DAY_ENABLED', True):
        deal_cards = _build_product_cards(all_products, 8)
    if not bestseller_cards and getattr(settings, 'HOME_BESTSELLER_ENABLED', True):
        bestseller_cards = _build_product_cards(all_products, 8)
    if not featured_cards and getattr(settings, 'HOME_FEATURED_ENABLED', True):
        featured_cards = _build_product_cards(all_products, 8)
 
    # ── Home category sections — batch fix for the N+1 ──
    #
    # BEFORE: for each HomeCategory → separate Product.objects.filter(pk__in=...) call
    # AFTER:  collect ALL product PKs across all sections, fetch once, distribute in Python
    home_category_sections = []
    try:
        active_home_cats = list(
            HomeCategory.objects.filter(is_active=True)
            .filter(Q(banner_image__isnull=False) & ~Q(banner_image=''))
            .select_related('linked_category')
            .prefetch_related(
                Prefetch(
                    'home_category_products',
                    queryset=HomeCategoryProduct.objects.select_related('product').order_by('display_order', 'id'),
                )
            )
            .order_by('display_order', 'name', 'id')
        )
 
        # Batch: collect all needed product PKs
        section_meta = []   # (hc, [ordered_product_ids])
        all_needed_pks = set()
        for hc in active_home_cats:
            links = [lnk for lnk in hc.home_category_products.all() if lnk.product and lnk.product.is_active]
            ordered_ids = [lnk.product_id for lnk in links]
            if ordered_ids:
                section_meta.append((hc, ordered_ids))
                all_needed_pks.update(ordered_ids)
 
        # ONE product query for all home-category sections combined
        if all_needed_pks:
            hc_products_qs = list(
                Product.objects.filter(pk__in=all_needed_pks)
                .select_related('category')
                .prefetch_related(variant_pf)
            )
            hc_by_id = {p.pk: p for p in hc_products_qs}
 
            for hc, ordered_ids in section_meta:
                sorted_products = [hc_by_id[pk] for pk in ordered_ids if pk in hc_by_id]
                card_products = _build_product_cards(sorted_products, 16)
                if card_products:
                    home_category_sections.append({'home_category': hc, 'products': card_products})
    except Exception as hc_exc:
        logger.error('Error building home category sections: %s', hc_exc, exc_info=True)
 
    # ── Rent products — small targeted query (separate flag, not in master qs) ──
    rent_cards = []
    try:
        rent_qs = list(
            Product.objects.filter(
                is_active=True,
                is_rent_available=True,
                rental_config__is_rent_enabled=True,
            )
            .select_related('category', 'rental_config')
            .prefetch_related(variant_pf)
            .order_by('-created_at')[:24]
        )
        rent_cards = _build_product_cards(rent_qs, 12)
        for p in rent_cards:
            if not getattr(p, 'rental_config', None):
                try:
                    from .models import RentalConfig
                    p.rental_config = RentalConfig.objects.filter(product=p).first()
                except Exception:
                    p.rental_config = None
    except Exception:
        pass
 
    # ── Static data — banners (tiny query, fast) ──
    try:
        banners = [b for b in Banner.objects.filter(is_active=True).order_by('display_order', 'created_at') if b.image]
    except Exception:
        banners = []
 
    data = {
        'deal_of_day_products':    deal_cards,
        'bestseller_products':     bestseller_cards,
        'new_arrival_products':    new_arrival_cards,
        'top_rated_products':      top_rated_cards,
        'budget_products':         budget_cards,
        'featured_products':       featured_cards,
        'beginner_friendly_products': beginner_cards,
        'home_category_sections':  home_category_sections,
        'rent_products':           rent_cards,
        'banners':                 banners,
    }
    _cache.set(CACHE_KEY, data, _HOME_CACHE_TTL)
    return data
 
 
def _cheapest_price(product):
    """Return the minimum sellable price for a product (Python-only, no DB)."""
    variants = list(getattr(product, 'sellable_variants', []) or [])
    if variants:
        return min(v.price for v in variants)
    return product.base_price
 
 
# ──────────────────────────────────────────────────────────────
# HomeView — OPTIMIZED
# ──────────────────────────────────────────────────────────────
 
class HomeView(TemplateView):
    template_name = 'pages/home.html'
 
    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)
 
            # ── 1. Cached heavy product data (1 cache read, or ~3 DB queries on miss) ──
            home_data = _load_home_product_data()
            context.update(home_data)
 
            # deal_products alias kept for template compatibility
            context['deal_products'] = context['deal_of_day_products']
 
            # Bestseller row split
            bs = list(context['bestseller_products'])
            mid = (len(bs) + 1) // 2
            context['bestseller_products_row1'] = bs[:mid]
            context['bestseller_products_row2'] = bs[mid:]
 
            # ── 2. Shop categories — cheap, small table, cached separately ──
            context['shop_categories'] = _load_shop_categories()
 
            # ── 3. Per-request: cart (must be live) ──
            try:
                cart = CartService.get_or_create_cart(self.request)
                items_qs = cart.items.select_related('product', 'selected_variant').prefetch_related('selected_variant__images')
                home_cart_items = list(items_qs)
                if home_cart_items:
                    context['home_cart'] = cart
                    context['home_cart_items'] = home_cart_items
                    context['home_cart_totals'] = CartService.compute_totals(cart)
                else:
                    context['home_cart_items'] = []
                cart_items_vals = list(
                    cart.items.filter(line_type=CartItem.LineKind.PURCHASE)
                    .values('product_id', 'selected_variant_id', 'combo_id')
                )
                context['cart_variant_ids']        = {i['selected_variant_id'] for i in cart_items_vals if i['selected_variant_id']}
                context['cart_product_ids']        = {i['product_id'] for i in cart_items_vals}
                context['cart_simple_product_ids'] = {i['product_id'] for i in cart_items_vals if not i['selected_variant_id']}
                context['cart_combo_ids']          = {i['combo_id'] for i in cart_items_vals if i['combo_id']}
            except Exception as cart_exc:
                logger.error('HomeView cart error: %s', cart_exc, exc_info=True)
                context['home_cart_items'] = []
                context['cart_variant_ids'] = set()
                context['cart_product_ids'] = set()
                context['cart_simple_product_ids'] = set()
                context['cart_combo_ids'] = set()
 
            # ── 4. Per-request: wishlist ──
            home_wishlist_variants = []
            user = getattr(self.request, 'user', None)
            if user and user.is_authenticated:
                try:
                    wishlist_items = list(
                        Wishlist.objects.filter(user=user)
                        .filter(selected_variant__is_active=True, selected_variant__product__is_active=True)
                        .select_related('selected_variant', 'selected_variant__product', 'selected_variant__product__category')
                        .prefetch_related('selected_variant__images')
                        .order_by('-created_at')[:12]
                    )
                    home_wishlist_variants = [wl.selected_variant for wl in wishlist_items if wl.selected_variant]
                except Exception as wl_exc:
                    logger.error('HomeView wishlist error: %s', wl_exc, exc_info=True)
            context['home_wishlist_variants'] = home_wishlist_variants
            context['home_wishlist_products'] = []
 
            # ── 5. Below-fold sections are lazy-loaded via AJAX ──
            # reels, testimonials, combos → served by HomeLazy* views below.
            # Template must call these endpoints on DOMContentLoaded.
            context['reels'] = []           # populated by /api/home/reels/
            context['testimonials'] = []    # populated by /api/home/testimonials/
            context['combo_products'] = []  # populated by /api/home/combos/
 
            context['active_page'] = 'home'
            return context
 
        except Exception as e:
            logger.error('HomeView.get_context_data error: %s', e, exc_info=True)
            context = super().get_context_data(**kwargs)
            context.update(_empty_home_context())
            return context
 
 
def _load_shop_categories():
    """Shop category list — cached for 5 minutes (rarely changes)."""
    CACHE_KEY = 'home_shop_categories_v1'
    cached = _cache.get(CACHE_KEY)
    if cached is not None:
        return cached
    qs = (
        Category.objects.filter(is_active=True, parent__isnull=True)
        .filter(
            Q(products__is_active=True, products__variants__is_active=True, products__variants__stock_quantity__gt=0)
            | Q(products__is_active=True, products__variants__isnull=True, products__base_stock__gt=0)
        )
        .distinct()
        .order_by('name')[:8]
    )
    result = list(qs)
    _cache.set(CACHE_KEY, result, 300)
    return result
 
 
def _empty_home_context():
    return {
        'active_page': 'home',
        'shop_categories': [],
        'featured_products': [],
        'deal_of_day_products': [],
        'deal_products': [],
        'bestseller_products': [],
        'bestseller_products_row1': [],
        'bestseller_products_row2': [],
        'new_arrival_products': [],
        'top_rated_products': [],
        'budget_products': [],
        'banners': [],
        'home_wishlist_variants': [],
        'home_wishlist_products': [],
        'beginner_friendly_products': [],
        'combo_products': [],
        'home_category_sections': [],
        'reels': [],
        'rent_products': [],
        'cart_combo_ids': set(),
        'testimonials': [],
        'home_cart_items': [],
        'cart_variant_ids': set(),
        'cart_product_ids': set(),
        'cart_simple_product_ids': set(),
    }
 
 
# ──────────────────────────────────────────────────────────────
# Lazy AJAX endpoints for below-fold home sections
# Wire these in urls.py (see bottom of file)
# ──────────────────────────────────────────────────────────────
 
class HomeLazyReelsView(View):
    """GET /api/home/reels/ — below-fold, not on critical path."""
 
    def get(self, request):
        CACHE_KEY = 'home_reels_v1'
        cached = _cache.get(CACHE_KEY)
        if cached is not None:
            return render(request, 'partials/_home_reels.html', {'reels': cached})
        try:
            reels_qs = list(
                __import__('app.models', fromlist=['Reel']).Reel.objects
                .filter(is_active=True)
                .exclude(video='')
                .select_related('product', 'product__category')
                .order_by('display_order', '-created_at')[:24]
            )
            sellable_variants_qs = (
                Variant.objects.filter(is_active=True, stock_quantity__gt=0)
                .prefetch_related('images')
                .order_by('display_order', 'id')
            )
            for r in reels_qs:
                p = getattr(r, 'product', None)
                if not p:
                    continue
                variants = list(getattr(p, 'sellable_variants', []) or [])
                if variants:
                    pv = min(variants, key=lambda v: (v.price, v.display_order, v.id))
                    p.primary_variant = pv
                    p.lowest_price = pv.price
                else:
                    p.primary_variant = None
                    p.lowest_price = p.base_price
            _cache.set(CACHE_KEY, reels_qs, _HOME_CACHE_TTL)
        except Exception:
            reels_qs = []
        return render(request, 'partials/_home_reels.html', {'reels': reels_qs})
 
 
class HomeLazyTestimonialsView(View):
    """GET /api/home/testimonials/"""
 
    def get(self, request):
        CACHE_KEY = 'home_testimonials_v1'
        cached = _cache.get(CACHE_KEY)
        if cached is not None:
            return render(request, 'partials/_home_testimonials.html', {'testimonials': cached})
        try:
            items = list(
                Testimonial.objects.filter(is_active=True)
                .order_by('display_order', '-created_at')[:12]
            )
        except Exception:
            items = []
        _cache.set(CACHE_KEY, items, _HOME_CACHE_TTL)
        return render(request, 'partials/_home_testimonials.html', {'testimonials': items})
 
 
class HomeLazyCombosView(View):
    """GET /api/home/combos/"""
 
    def get(self, request):
        CACHE_KEY = 'home_combos_v1'
        cached = _cache.get(CACHE_KEY)
        if cached is not None:
            return render(request, 'partials/_home_combos.html', {'combo_products': cached})
        try:
            from .services.combo_catalog import combo_is_in_stock, prefetch_combo_items
            combo_qs = (
                Combo.objects.filter(is_active=True, purchase_enabled=True, show_in_combos_nav=True)
                .prefetch_related(prefetch_combo_items())
                .order_by('-updated_at')
            )
            combo_cards = []
            for c in combo_qs[:12]:
                if c.price and combo_is_in_stock(c, multiplier=1):
                    combo_cards.append(c)
                if len(combo_cards) >= 8:
                    break
        except Exception:
            combo_cards = []
        _cache.set(CACHE_KEY, combo_cards, _HOME_CACHE_TTL)
        return render(request, 'partials/_home_combos.html', {'combo_products': combo_cards})
 
 
# ──────────────────────────────────────────────────────────────
# ProductListView — OPTIMIZED
# ──────────────────────────────────────────────────────────────
 
# ─────────────────────────────────────────────────────────────────────────────
# CHANGES vs original:
#   1. paginate_by = 20  (was 12)
#   2. get() sets  X-Has-Next-Page  header on AJAX responses so the JS knows
#      whether to stop the IntersectionObserver or keep watching.
# ─────────────────────────────────────────────────────────────────────────────

class ProductListView(ListView):
    template_name = 'pages/shop.html'
    context_object_name = 'card_items'
    paginate_by = 20                          # ← changed from 12

    def get_queryset(self):
        try:
            combo_only = (self.request.GET.get('combo') or '').strip().lower() in ('1', 'true', 'yes')
            if combo_only:
                return collection_combo_cards(self.request)
            return collection_card_items(self.request, self.paginate_by)
        except Exception as e:
            logger.error('ProductListView.get_queryset error: %s', e, exc_info=True)
            return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request

        tree = build_active_category_tree()
        root_ids = tree.children_ids.get(None, [])
        root_categories = [tree.by_id[cid] for cid in root_ids if cid in tree.by_id]

        context['products']    = context.get('card_items', [])
        context['page_title']  = 'Shop'
        context['active_page'] = 'collection'

        category_slug = request.GET.get('category')
        selected_category = None
        selected_child_categories = []

        if category_slug and category_slug != 'all':
            selected_category, _ids = category_filter_ids_for_slug(
                category_slug, include_children=True, max_depth=10
            )
            if selected_category:
                context['page_title'] = selected_category.name

        if selected_category:
            parent_id = selected_category.parent_id
            if parent_id:
                selected_child_categories = [
                    tree.by_id[cid]
                    for cid in tree.children_ids.get(parent_id, [])
                    if cid in tree.by_id
                ]
            else:
                selected_child_categories = [
                    tree.by_id[cid]
                    for cid in tree.children_ids.get(selected_category.pk, [])
                    if cid in tree.by_id
                ]

        shop_banner_url      = None
        shop_banner_tagline  = ''
        if selected_category:
            shop_banner_url     = selected_category.get_shop_banner_url()
            shop_banner_tagline = (getattr(selected_category, 'banner_tagline', '') or '').strip()
        context['shop_category_banner'] = (
            {'url': shop_banner_url, 'tagline': shop_banner_tagline} if shop_banner_url else None
        )

        context['categories']       = root_categories
        context['child_categories'] = selected_child_categories
        context['selected_category'] = selected_category

        min_price  = request.GET.get('min_price', '')
        max_price  = request.GET.get('max_price', '')
        query      = request.GET.get('q', '')
        sort       = request.GET.get('sort', 'newest')
        rent_only  = (request.GET.get('rent')  or '').strip() in ('1', 'true', 'yes')
        combo_only = (request.GET.get('combo') or '').strip().lower() in ('1', 'true', 'yes')

        context['combo_only'] = combo_only
        if combo_only:
            context['page_title'] = 'Combos'

        context['filters'] = {
            'category':   category_slug or 'all',
            'min_price':  min_price,
            'max_price':  max_price,
            'q':          query,
            'sort':       sort,
            'difficulty': request.GET.get('difficulty', ''),
            'sunlight':   request.GET.get('sunlight', ''),
            'watering':   request.GET.get('watering', ''),
            'plant_type': request.GET.get('plant_type', ''),
            'guide':      request.GET.get('guide', ''),
            'combo':      request.GET.get('combo', ''),
            'rent':       request.GET.get('rent', ''),
        }
        context['sort_options'] = [
            ('newest',     'Newest'),
            ('price_asc',  'Price: Low to High'),
            ('price_desc', 'Price: High to Low'),
        ]

        if combo_only:
            context['simple_products']      = []
            context['total_product_count']  = len(context.get('card_items', []))
        else:
            simple_qs = (
                Product.objects.active()
                .filter(variants__isnull=True)
                .filter(Q(base_stock__gt=0) | Q(is_combo_product=True))
                .select_related('category')
                .prefetch_related('images')
            )
            if rent_only:
                simple_qs = simple_qs.filter(
                    is_rent_available=True,
                    rental_config__is_rent_enabled=True,
                ).select_related('rental_config')
            if category_slug and category_slug != 'all':
                _, ids = category_filter_ids_for_slug(category_slug, include_children=True, max_depth=10)
                if ids:
                    simple_qs = simple_qs.filter(category_id__in=ids)
            if min_price:
                simple_qs = simple_qs.filter(base_price__gte=min_price)
            if max_price:
                simple_qs = simple_qs.filter(base_price__lte=max_price)
            if query:
                simple_qs = simple_qs.filter(
                    Q(name__icontains=query)
                    | Q(description__icontains=query)
                    | Q(category__name__icontains=query)
                )
            simple_qs = apply_plant_filters_to_product_qs(simple_qs, request)
            if sort == 'price_asc':
                simple_qs = simple_qs.order_by('base_price', 'created_at')
            elif sort == 'price_desc':
                simple_qs = simple_qs.order_by('-base_price', '-created_at')
            else:
                simple_qs = simple_qs.order_by('-created_at', 'name', 'id')
            context['simple_products']     = list(simple_qs)
            context['total_product_count'] = (
                len(context.get('card_items', [])) + len(context['simple_products'])
            )

        # ── Cart state (per-request, must stay live) ──
        try:
            cart       = CartService.get_or_create_cart(request)
            cart_items = list(
                cart.items.filter(line_type=CartItem.LineKind.PURCHASE)
                .values('product_id', 'selected_variant_id', 'combo_id')
            )
            context['cart_variant_ids']        = {i['selected_variant_id'] for i in cart_items if i['selected_variant_id']}
            context['cart_product_ids']        = {i['product_id']          for i in cart_items if i['product_id']}
            context['cart_simple_product_ids'] = {i['product_id']          for i in cart_items if i['product_id'] and not i['selected_variant_id']}
            context['cart_combo_ids']          = {i['combo_id']            for i in cart_items if i['combo_id']}
        except Exception:
            context['cart_variant_ids']        = set()
            context['cart_product_ids']        = set()
            context['cart_simple_product_ids'] = set()
            context['cart_combo_ids']          = set()

        return context

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        context          = self.get_context_data()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # ── AJAX / infinite-scroll request ──
            # Render only the cards fragment (no full page shell)
            response = render(request, 'partials/_shop_cards_fragment.html', context)

            # ─────────────────────────────────────────────────────────────────
            # X-Has-Next-Page header
            # The JS reads this to decide whether to keep observing the sentinel
            # or disconnect and show the "You've seen everything" end message.
            #
            # page_obj is set by ListView's paginate_queryset(); it's always
            # present when paginate_by is set.
            # ─────────────────────────────────────────────────────────────────
            page_obj = context.get('page_obj')
            has_next = 'true' if (page_obj and page_obj.has_next()) else 'false'
            response['X-Has-Next-Page'] = has_next

            return response

        # Normal full-page render
        return self.render_to_response(context)


RECENTLY_VIEWED_MAX          = 20
RECENTLY_VIEWED_VARIANTS_MAX = 20

def _update_recently_viewed(session, product_id):
    if not product_id:
        return
    ids = list(session.get('recently_viewed_ids', []))
    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        return
    if pid in ids:
        ids.remove(pid)
    ids.append(pid)
    ids = ids[-RECENTLY_VIEWED_MAX:]
    session['recently_viewed_ids'] = ids
    session.modified = True

def _update_recently_viewed_variant(session, variant_id):
    if not variant_id:
        return
    ids = list(session.get('recently_viewed_variant_ids', []))
    try:
        vid = int(variant_id)
    except (TypeError, ValueError):
        return
    if vid in ids:
        ids.remove(vid)
    ids.append(vid)
    ids = ids[-RECENTLY_VIEWED_VARIANTS_MAX:]
    session['recently_viewed_variant_ids'] = ids
    session.modified = True

class ComboDetailView(DetailView):
    template_name = 'pages/combo.html'
    context_object_name = 'combo'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return Combo.objects.filter(is_active=True).prefetch_related(
            Prefetch('items', queryset=ComboItem.objects.select_related('product').order_by('display_order', 'id'))
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from .services.combo_catalog import combo_is_in_stock

        obj = self.object
        rows = list(obj.items.all())
        ctx['combo_lines'] = [{'name': r.product.name, 'quantity': r.quantity, 'product_slug': r.product.slug} for r in rows]
        ctx['pdp_combo_available'] = bool(rows) and combo_is_in_stock(obj, multiplier=1)
        ctx['active_page'] = 'collection'
        try:
            cart = CartService.get_or_create_cart(self.request)
            ctx['cart_combo_ids'] = set(cart.items.filter(line_type=CartItem.LineKind.PURCHASE).values_list('combo_id', flat=True))
            ctx['cart_combo_ids'].discard(None)
        except Exception:
            ctx['cart_combo_ids'] = set()
        return ctx


class ProductDetailView(DetailView):
    template_name = 'pages/product.html'
    context_object_name = 'product'
    slug_url_kwarg = 'slug'

    def get(self, request, *args, **kwargs):
        slug = kwargs.get(self.slug_url_kwarg) or self.kwargs.get('slug')
        prod_early = Product.objects.filter(slug=slug).first()
        if prod_early and getattr(prod_early, 'is_legacy_combo', False):
            repl = getattr(prod_early, 'replaced_by_combo', None)
            if repl and getattr(repl, 'is_active', True):
                return redirect('store:combo_detail', slug=repl.slug)
        self.object = self.get_object()
        _update_recently_viewed(request.session, self.object.pk)
        variant_param = request.GET.get('variant')
        if variant_param:
            try:
                vid = int(variant_param)
                if Variant.objects.filter(pk=vid, product=self.object).exists():
                    _update_recently_viewed_variant(request.session, vid)
            except (TypeError, ValueError):
                pass
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return get_pdp_queryset()

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)
            product = context['product']
            context.update(ProductDetailService.augment_context(self.request, product))
            return context
        except Exception as e:
            logger.error(f'Error in ProductDetailView.get_context_data: {str(e)}', exc_info=True)
            raise


class ProductPdpReviewsFragmentView(View):
    """Lazy-loaded reviews + write form (reduces initial PDP query/render cost)."""

    def get(self, request, slug, *args, **kwargs):
        product = get_object_or_404(get_pdp_queryset(), slug=slug)
        ctx = ProductDetailService.build_reviews_context(request, product)
        return render(request, 'sections/product_reviews.html', ctx)


class ProductPdpSeoFragmentView(View):
    """Lazy-loaded long-form SEO block."""

    def get(self, request, slug, *args, **kwargs):
        product = get_object_or_404(Product.objects.active().select_related('extended_content'), slug=slug)
        return render(request, 'sections/product_seo.html', {'product': product})


class ProductDeliveryStatesView(View):
    """
    Return the deliverable state list for a product.
    Called on initial PDP load to populate the state dropdown.
 
    GET /api/delivery/states/?product_id=42
 
    Response:
    {
        "states": [
            {"id": 1, "name": "Kerala",     "code": "KL", "region": "south"},
            {"id": 2, "name": "Tamil Nadu", "code": "TN", "region": "south"},
            ...
        ]
    }
    """
 
    def get(self, request, *args, **kwargs):
        from app.services.state_delivery_service import get_deliverable_states_payload

        raw = request.GET.get("product_id", "")
        try:
            product_id = int(raw)
        except (ValueError, TypeError):
            return JsonResponse(
                {"states": [], "error": "product_id is required and must be an integer."},
                status=400,
            )

        return JsonResponse({"states": get_deliverable_states_payload(product_id)})
 
 
class StateServiceabilityView(View):
    """
    Check if a specific state is serviceable for a product.
    Called when the customer selects a state on the PDP dropdown.
 
    GET /api/delivery/state/?product_id=42&state_id=5
 
    Response (serviceable):
    {
        "serviceable": true,
        "state_id": 5,
        "state_name": "Tamil Nadu",
        "deliverable_states": [...],
        "message": "Delivery available to Tamil Nadu ✓"
    }
 
    Response (not serviceable):
    {
        "serviceable": false,
        "state_id": 30,
        "state_name": "West Bengal",
        "deliverable_states": [...],
        "message": "Sorry, we don't currently deliver to West Bengal."
    }
    """
 
    def get(self, request, *args, **kwargs):
        from app.services.state_delivery_service import serviceability_payload, serviceability_payload_for_combo

        raw_product = request.GET.get("product_id", "")
        raw_combo = request.GET.get("combo_id", "")
        raw_state   = request.GET.get("state_id", "")

        try:
            state_id = int(raw_state) if raw_state else None
        except (ValueError, TypeError):
            state_id = None

        if raw_combo:
            try:
                combo_id = int(raw_combo)
            except (ValueError, TypeError):
                return JsonResponse(
                    {"serviceable": False, "message": "combo_id is invalid."},
                    status=400,
                )
            payload = serviceability_payload_for_combo(combo_id=combo_id, state_id=state_id)
            return JsonResponse(payload)

        try:
            product_id = int(raw_product)
        except (ValueError, TypeError):
            return JsonResponse(
                {"serviceable": False, "message": "product_id is required."},
                status=400,
            )

        payload = serviceability_payload(product_id=product_id, state_id=state_id)
        return JsonResponse(payload)
 
 
class ComboDeliveryStatesView(View):
    """
    Return deliverable states for a combo (intersection of all components).
    Called on initial Combo PDP load.
 
    GET /api/delivery/states/combo/?combo_id=7
    """
 
    def get(self, request, *args, **kwargs):
        from app.services.state_delivery_service import serviceability_payload_for_combo
 
        raw = request.GET.get("combo_id", "")
        try:
            combo_id = int(raw)
        except (ValueError, TypeError):
            return JsonResponse(
                {"states": [], "error": "combo_id is required."},
                status=400,
            )
 
        payload = serviceability_payload_for_combo(combo_id=combo_id, state_id=None)
        return JsonResponse({"states": payload["deliverable_states"]})
 
 
# ── Legacy stub — keeps old PDP JS working until templates are updated ─────────
 
class PincodeServiceabilityView(View):
    """
    DEPRECATED. Kept so old AJAX calls don't 404 during template migration.
    Always returns serviceable=false with a migration message.
    Remove once all templates use the new state-based endpoints.
    """
 
    def get(self, request, *args, **kwargs):
        return JsonResponse({
            "serviceable": False,
            "normalized": "",
            "message": (
                "PIN code checks are no longer used. "
                "Please select your state from the dropdown."
            ),
            "_deprecated": True,
        })


class ProductReviewCreateView(LoginRequiredForActionMixin, View):
    http_method_names = ['post']

    def post(self, request, product_id: int, *args, **kwargs):
        if not getattr(settings, 'REVIEW_ENABLED', True):
            raise Http404('Reviews are not enabled.')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if not request.user.is_authenticated:
            login_url = f"{reverse('auth:login')}?next={request.build_absolute_uri()}"
            if is_ajax:
                return JsonResponse({'success': False, 'login_required': True, 'login_url': login_url, 'error': 'Login required to write a review.'}, status=403)
            return redirect(login_url)
        product = get_object_or_404(Product, pk=product_id, is_active=True)
        form = ReviewForm(request.POST)
        if not form.is_valid():
            if is_ajax:
                error_text = '; '.join([f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()]) or 'Invalid review data.'
                return JsonResponse({'success': False, 'error': error_text}, status=400)
            messages.error(request, 'Invalid review data.')
            return redirect('store:product_detail', slug=product.slug)
        delivered_qs = OrderItem.objects.select_related('order').filter(order__user=request.user, order__status=Order.Status.DELIVERED, product=product).order_by('-order__created_at')
        delivered_item = delivered_qs.first()
        if not delivered_item:
            msg = 'You can only review products you have received (delivered orders only).'
            if is_ajax:
                return JsonResponse({'success': False, 'error': msg}, status=403)
            messages.error(request, msg)
            return redirect('store:product_detail', slug=product.slug)
        if Review.objects.filter(product=product, user=request.user).exists():
            msg = 'You have already reviewed this product.'
            if is_ajax:
                return JsonResponse({'success': False, 'error': msg}, status=400)
            messages.error(request, msg)
            return redirect('store:product_detail', slug=product.slug)
        try:
            with transaction.atomic():
                Review.objects.create(product=product, user=request.user, order=delivered_item.order, rating=form.cleaned_data['rating'], title=form.cleaned_data.get('title', '').strip(), comment=form.cleaned_data.get('comment', '').strip())
        except IntegrityError:
            msg = 'You have already reviewed this product.'
            if is_ajax:
                return JsonResponse({'success': False, 'error': msg}, status=400)
            messages.error(request, msg)
            return redirect('store:product_detail', slug=product.slug)
        except Exception as exc:
            logger.error('Error creating review: %s', exc, exc_info=True)
            msg = 'Could not submit your review. Please try again.'
            if is_ajax:
                return JsonResponse({'success': False, 'error': msg}, status=500)
            messages.error(request, msg)
            return redirect('store:product_detail', slug=product.slug)
        success_msg = 'Thank you for your review!'
        if is_ajax:
            return JsonResponse({'success': True, 'message': success_msg})
        messages.success(request, success_msg)
        return redirect('store:product_detail', slug=product.slug)

def _normalize_image_url(url):
    if not url or not isinstance(url, str):
        return url
    url = url.strip()
    if url.startswith('http://') or url.startswith('https://'):
        return url
    if url.startswith('/'):
        base = getattr(settings, 'MEDIA_URL', '/media/').rstrip('/')
        if base and url.startswith(base + '/') and ('ytimg.com' in url):
            return 'https://' + url[len(base) + 1:]
        return url
    return 'https://' + url.lstrip('/')

class ProductColorImagesView(View):

    def get(self, request, *args, **kwargs):
        variant_id = request.GET.get('variant_id')
        product_id = request.GET.get('product_id')
        if not variant_id:
            return JsonResponse({'images': []})
        try:
            vid = int(variant_id)
        except (ValueError, TypeError):
            return JsonResponse({'images': []})
        variant = Variant.objects.filter(pk=vid).prefetch_related('images').first()
        if product_id and variant and (variant.product_id != int(product_id)):
            variant = None
        if not variant:
            return JsonResponse({'images': []})
        images = []
        for img in variant.images.filter(image__isnull=False).exclude(image='').order_by('display_order', '-is_primary', 'id'):
            if img.image:
                try:
                    raw_url = img.image.url
                    url = _normalize_image_url(raw_url)
                    if url.startswith('/'):
                        url = request.build_absolute_uri(url)
                    images.append({'url': url, 'is_primary': getattr(img, 'is_primary', False)})
                except Exception:
                    pass
        return JsonResponse({'images': images})

class ProductVariantResolveView(View):

    def _get_ids(self, request):
        product_id = request.GET.get('product_id') or (request.POST.get('product_id') if request.method == 'POST' else None)
        ids_raw = request.GET.get('attribute_value_ids') or (request.POST.get('attribute_value_ids') if request.method == 'POST' else None)
        if request.body and request.content_type and ('application/json' in (request.content_type or '')):
            try:
                data = json.loads(request.body)
                product_id = product_id or data.get('product_id')
                ids_raw = ids_raw or data.get('attribute_value_ids')
                if isinstance(ids_raw, list):
                    return (product_id, [int(x) for x in ids_raw if x is not None])
            except (json.JSONDecodeError, TypeError):
                pass
        if ids_raw is None:
            return (product_id, [])
        if isinstance(ids_raw, str) and ',' in ids_raw:
            ids = [int(x.strip()) for x in ids_raw.split(',') if x.strip().isdigit()]
        elif isinstance(ids_raw, list):
            ids = [int(x) for x in ids_raw if x is not None]
        else:
            try:
                ids = [int(ids_raw)]
            except (TypeError, ValueError):
                ids = []
        return (product_id, ids)

    def get(self, request):
        product_id, attr_value_ids = self._get_ids(request)
        if not product_id:
            return JsonResponse({'success': False, 'error': 'product_id required'}, status=400)
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid product_id'}, status=400)
        product = Product.objects.filter(pk=product_id, is_active=True).first()
        if not product:
            return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)
        value_ids = set(attr_value_ids)
        variant = None
        for v in product.variants.filter(is_active=True).prefetch_related('images', 'attribute_values'):
            v_ids = set(v.attribute_values.values_list('id', flat=True))
            if v_ids == value_ids:
                variant = v
                break
        if not variant:
            return JsonResponse({'success': False, 'error': 'Variant not found', 'variant': None}, status=404)
        images = list(variant.images.order_by('display_order', '-is_primary', 'id'))
        image_urls = []
        for img in images:
            if img.image:
                try:
                    u = img.image.url
                    if u and u.startswith('/'):
                        u = request.build_absolute_uri(u)
                    image_urls.append(u)
                except Exception:
                    pass
        return JsonResponse({'success': True, 'variant': {'id': variant.id, 'price': str(variant.price), 'stock_quantity': variant.stock_quantity, 'in_stock': (variant.stock_quantity or 0) > 0, 'image_urls': image_urls, 'variant_display': variant.get_attribute_values_display()}})

    def post(self, request):
        return self.get(request)

def _serialize_variant_for_json(variant, detail_url=None):
    product = getattr(variant, 'product', None)
    if not product:
        return {}
    if detail_url is None:
        base = reverse('store:product_detail', args=[product.slug])
        detail_url = f'{base}?variant={variant.id}'
    card_images = []
    for img in getattr(variant, 'images', None).all() or []:
        if getattr(img, 'image', None):
            try:
                u = img.image.url
                if u:
                    u = _normalize_image_url(u)
                    card_images.append(u)
            except Exception:
                pass
    image_url = card_images[0] if card_images else '/static/images/banner.png'
    has_stock = (variant.stock_quantity or 0) > 0
    _threshold = getattr(product, 'low_stock_threshold', None) or getattr(settings, 'LOW_STOCK_THRESHOLD', 5)
    is_low_stock = 0 < (variant.stock_quantity or 0) <= _threshold
    category_name = product.category.name if getattr(product, 'category', None) else ''
    avg_rating = getattr(product, 'average_rating', None)
    if avg_rating is not None:
        avg_rating = float(avg_rating)
    total_reviews = getattr(product, 'total_reviews', None)
    if total_reviews is not None:
        total_reviews = int(total_reviews)
    return {'id': product.id, 'variant_id': variant.id, 'name': product.name or '', 'slug': product.slug or '', 'variant_display': variant.get_attribute_values_display(), 'price': str(variant.price), 'url': detail_url, 'image_url': image_url, 'card_images': card_images, 'category_name': category_name or '', 'has_stock': has_stock, 'is_low_stock': is_low_stock, 'average_rating': avg_rating, 'total_reviews': total_reviews, 'is_featured': getattr(product, 'is_featured', False), 'is_active': getattr(product, 'is_active', True), 'description': getattr(product, 'description', '') or ''}

class NewArrivalsView(View):

    def get(self, request):
        try:
            limit = request.GET.get('limit', '30')
            try:
                limit = min(max(int(limit), 1), 30)
            except (TypeError, ValueError):
                limit = 30
            qs = active_variant_qs().order_by('-product__created_at', 'display_order', 'id')
            seen_products = set()
            variants = []
            for v in qs:
                if v.product_id in seen_products:
                    continue
                seen_products.add(v.product_id)
                variants.append(v)
                if len(variants) >= limit:
                    break
            payload = [_serialize_variant_for_json(v) for v in variants]
            return JsonResponse({'products': payload})
        except Exception as e:
            logger.exception('NewArrivalsView: %s', e)
            return JsonResponse({'products': []})

class TopSellingView(View):

    def get(self, request):
        try:
            limit = request.GET.get('limit', '8')
            try:
                limit = min(max(int(limit), 1), 24)
            except (TypeError, ValueError):
                limit = 8
            order_filter = ~Q(order__status=Order.Status.CANCELLED)
            product_ids_with_qty = OrderItem.objects.filter(order_filter).values('product_id').annotate(total_sold=Sum('quantity')).filter(total_sold__gt=0, product__is_active=True).order_by('-total_sold')[:limit * 2]
            ids_ordered = [x['product_id'] for x in product_ids_with_qty]
            if not ids_ordered:
                return JsonResponse({'products': []})
            preserved_order = dict(((pk, i) for i, pk in enumerate(ids_ordered)))
            qs = active_variant_qs().filter(product_id__in=ids_ordered)
            seen_products = set()
            variants = []
            for v in sorted(qs, key=lambda x: (preserved_order.get(x.product_id, 999), x.display_order, x.id)):
                if v.product_id in seen_products:
                    continue
                seen_products.add(v.product_id)
                variants.append(v)
                if len(variants) >= limit:
                    break
            payload = [_serialize_variant_for_json(v) for v in variants]
            return JsonResponse({'products': payload})
        except Exception as e:
            logger.exception('TopSellingView: %s', e)
            return JsonResponse({'products': []})

class RecentlyViewedView(View):

    def get(self, request):
        try:
            raw_ids = list(request.session.get('recently_viewed_variant_ids', []))
            if not raw_ids:
                return JsonResponse({'products': []})
            seen = set()
            unique_ids = []
            for pk in raw_ids:
                try:
                    pk_int = int(pk)
                except (TypeError, ValueError):
                    continue
                if pk_int in seen:
                    continue
                seen.add(pk_int)
                unique_ids.append(pk_int)
            ids = unique_ids[-RECENTLY_VIEWED_VARIANTS_MAX:]
            if not ids:
                return JsonResponse({'products': []})
            preserved_order = dict(((pk, i) for i, pk in enumerate(ids)))
            qs = active_variant_qs().filter(pk__in=ids)
            variants = sorted(list(qs), key=lambda v: preserved_order.get(v.pk, 999))
            payload = [_serialize_variant_for_json(v) for v in variants]
            return JsonResponse({'products': payload})
        except Exception as e:
            logger.exception('RecentlyViewedView: %s', e)
            return JsonResponse({'products': []})

class YouMayLikeView(View):

    def get(self, request):
        try:
            limit = 16
            payload = []
            raw_ids = list(request.session.get('recently_viewed_variant_ids', []))
            viewed_product_ids = set()
            viewed_variant_ids = set()
            if raw_ids:
                seen = set()
                variant_ids = []
                for val in raw_ids:
                    try:
                        vid = int(val)
                    except (TypeError, ValueError):
                        continue
                    if vid in seen:
                        continue
                    seen.add(vid)
                    variant_ids.append(vid)
                viewed_variants = list(active_variant_qs().filter(pk__in=variant_ids))
                viewed_variant_ids = {v.pk for v in viewed_variants}
                viewed_product_ids = {v.product_id for v in viewed_variants}
                if viewed_product_ids:
                    base_qs = active_variant_qs().filter(product_id__in=viewed_product_ids).exclude(pk__in=viewed_variant_ids)
                    candidates = list(base_qs.order_by('product__name', 'display_order', 'id')[:limit])
                    payload = [_serialize_variant_for_json(v) for v in candidates]
            return JsonResponse({'products': payload})
        except Exception as e:
            logger.exception('YouMayLikeView: %s', e)
            return JsonResponse({'products': []})

class WishlistToggleView(View):

    def post(self, request):
        if not wishlist_enabled():
            return JsonResponse({'success': False, 'error': 'Wishlist is currently disabled.'}, status=403)
        variant_id = None
        product_id = None
        if request.content_type and 'application/json' in request.content_type:
            try:
                data = json.loads(request.body)
                variant_id = data.get('selected_variant_id') or data.get('variant_id')
                product_id = data.get('product_id')
            except (json.JSONDecodeError, TypeError):
                pass
        if variant_id is None:
            variant_id = request.POST.get('selected_variant_id') or request.POST.get('variant_id')
        if product_id is None:
            product_id = request.POST.get('product_id')
        try:
            variant_id = int(variant_id) if variant_id else None
        except (TypeError, ValueError):
            variant_id = None
        try:
            product_id = int(product_id) if product_id else None
        except (TypeError, ValueError):
            product_id = None
        if variant_id and product_id:
            return JsonResponse({'success': False, 'error': 'Send either variant_id or product_id, not both.'}, status=400)
        if not variant_id and not product_id:
            return JsonResponse({'success': False, 'error': 'Variant or product required'}, status=400)

        if variant_id:
            v = Variant.objects.filter(pk=variant_id, is_active=True, product__is_active=True).select_related('product').first()
            if not v:
                return JsonResponse({'success': False, 'error': 'Variant not found'}, status=404)
            if not request.user.is_authenticated:
                ids = get_guest_wishlist_variant_ids(request)
                if variant_id in ids:
                    ids = [x for x in ids if x != variant_id]
                    added = False
                else:
                    if guest_wishlist_room_left(request) < 1:
                        return JsonResponse({'success': False, 'error': 'Wishlist is full (max 50 items).'}, status=400)
                    ids.append(variant_id)
                    added = True
                set_guest_wishlist_variant_ids(request, ids)
                return JsonResponse({'success': True, 'added': added, 'count': guest_wishlist_total_count(request)})
            wishlist, created = Wishlist.objects.get_or_create(user=request.user, selected_variant=v, defaults={'product': None})
            if not created:
                wishlist.delete()
                added = False
            else:
                added = True
            count = Wishlist.objects.filter(user=request.user).count()
            return JsonResponse({'success': True, 'added': added, 'count': count})

        p = Product.objects.filter(pk=product_id, is_active=True).first()
        if not p or p.has_variants():
            return JsonResponse({'success': False, 'error': 'Product not found or not a simple product'}, status=404)
        if not request.user.is_authenticated:
            ids = get_guest_wishlist_product_ids(request)
            if product_id in ids:
                ids = [x for x in ids if x != product_id]
                added = False
            else:
                if guest_wishlist_room_left(request) < 1:
                    return JsonResponse({'success': False, 'error': 'Wishlist is full (max 50 items).'}, status=400)
                ids.append(product_id)
                added = True
            set_guest_wishlist_product_ids(request, ids)
            return JsonResponse({'success': True, 'added': added, 'count': guest_wishlist_total_count(request)})
        wishlist, created = Wishlist.objects.get_or_create(user=request.user, product=p, defaults={'selected_variant': None})
        if not created:
            wishlist.delete()
            added = False
        else:
            added = True
        count = Wishlist.objects.filter(user=request.user).count()
        return JsonResponse({'success': True, 'added': added, 'count': count})

class RemoveFromWishlistView(View):

    def post(self, request):
        if not wishlist_enabled():
            return JsonResponse({'success': False, 'error': 'Wishlist is currently disabled.'}, status=403)
        variant_id = request.POST.get('selected_variant_id') or request.POST.get('variant_id')
        product_id = request.POST.get('product_id')
        if request.content_type and 'application/json' in request.content_type and request.body:
            try:
                data = json.loads(request.body)
                variant_id = variant_id or data.get('selected_variant_id') or data.get('variant_id')
                product_id = product_id or data.get('product_id')
            except (json.JSONDecodeError, TypeError):
                pass
        try:
            vid = int(variant_id) if variant_id else None
        except (TypeError, ValueError):
            vid = None
        try:
            pid = int(product_id) if product_id else None
        except (TypeError, ValueError):
            pid = None
        if vid and pid:
            return JsonResponse({'success': False, 'error': 'Send either variant_id or product_id'}, status=400)
        if not vid and not pid:
            return JsonResponse({'success': False, 'error': 'Variant or product required'}, status=400)
        if vid:
            if not request.user.is_authenticated:
                ids = get_guest_wishlist_variant_ids(request)
                if vid not in ids:
                    return JsonResponse({'success': True, 'removed': False, 'count': guest_wishlist_total_count(request)})
                ids = [x for x in ids if x != vid]
                set_guest_wishlist_variant_ids(request, ids)
                return JsonResponse({'success': True, 'removed': True, 'count': guest_wishlist_total_count(request)})
            deleted = Wishlist.objects.filter(user=request.user, selected_variant_id=vid).delete()[0]
            count = Wishlist.objects.filter(user=request.user).count()
            return JsonResponse({'success': True, 'removed': deleted > 0, 'count': count})
        if not request.user.is_authenticated:
            ids = get_guest_wishlist_product_ids(request)
            if pid not in ids:
                return JsonResponse({'success': True, 'removed': False, 'count': guest_wishlist_total_count(request)})
            ids = [x for x in ids if x != pid]
            set_guest_wishlist_product_ids(request, ids)
            return JsonResponse({'success': True, 'removed': True, 'count': guest_wishlist_total_count(request)})
        deleted = Wishlist.objects.filter(user=request.user, product_id=pid).delete()[0]
        count = Wishlist.objects.filter(user=request.user).count()
        return JsonResponse({'success': True, 'removed': deleted > 0, 'count': count})

class WishlistIdsView(View):

    def get(self, request):
        if not wishlist_enabled():
            return JsonResponse({'variant_ids': [], 'product_ids': []})
        if not request.user.is_authenticated:
            return JsonResponse({
                'variant_ids': get_guest_wishlist_variant_ids(request),
                'product_ids': get_guest_wishlist_product_ids(request),
            })
        try:
            variant_ids = list(
                Wishlist.objects.filter(user=request.user, selected_variant__isnull=False)
                .filter(selected_variant__is_active=True, selected_variant__product__is_active=True)
                .values_list('selected_variant_id', flat=True)
            )
            product_ids = list(
                Wishlist.objects.filter(user=request.user, product__isnull=False)
                .filter(product__is_active=True)
                .values_list('product_id', flat=True)
            )
            return JsonResponse({'variant_ids': variant_ids, 'product_ids': product_ids})
        except Exception as e:
            logger.exception('WishlistIdsView: %s', e)
            return JsonResponse({'variant_ids': [], 'product_ids': []})

class WishlistPageView(TemplateView):
    template_name = 'pages/wishlist.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not wishlist_enabled():
            context['wishlist_items'] = []
            context['active_page'] = 'collection'
            return context

        class GuestWishlistItem:
            __slots__ = ('selected_variant', 'product')

            def __init__(self, variant=None, product=None):
                self.selected_variant = variant
                self.product = product

        if not self.request.user.is_authenticated:
            v_ids = get_guest_wishlist_variant_ids(self.request)
            p_ids = get_guest_wishlist_product_ids(self.request)
            if not v_ids and not p_ids:
                context['wishlist_items'] = []
                context['active_page'] = 'wishlist'
                return context
            variants = list(
                Variant.objects.filter(pk__in=v_ids, is_active=True, product__is_active=True)
                .exclude(product__slug='')
                .select_related('product', 'product__category')
                .prefetch_related('images')
            )
            products = list(
                Product.objects.filter(pk__in=p_ids, is_active=True)
                .annotate(_vc=Count('variants'))
                .filter(_vc=0)
                .exclude(slug='')
                .select_related('category')
                .prefetch_related('images')
            )
            by_vid = {v.pk: v for v in variants}
            by_pid = {p.pk: p for p in products}
            merged = []
            for vid in v_ids:
                if vid in by_vid:
                    merged.append(GuestWishlistItem(variant=by_vid[vid]))
            for pid in p_ids:
                if pid in by_pid:
                    merged.append(GuestWishlistItem(product=by_pid[pid]))
            context['wishlist_items'] = merged
            context['active_page'] = 'wishlist'
            try:
                cart = CartService.get_or_create_cart(self.request)
                cart_items = list(cart.items.filter(line_type=CartItem.LineKind.PURCHASE).values('product_id', 'selected_variant_id'))
                context['cart_variant_ids'] = set((i['selected_variant_id'] for i in cart_items if i['selected_variant_id']))
                context['cart_simple_product_ids'] = set((i['product_id'] for i in cart_items if not i['selected_variant_id']))
            except Exception:
                context['cart_variant_ids'] = set()
                context['cart_simple_product_ids'] = set()
            return context

        wishlist_items = (
            Wishlist.objects.filter(user=self.request.user)
            .filter(
                Q(selected_variant__isnull=False, selected_variant__is_active=True, selected_variant__product__is_active=True)
                | Q(product__isnull=False, product__is_active=True)
            )
            .exclude(
                Q(selected_variant__isnull=False, selected_variant__product__slug='')
                | Q(product__isnull=False, product__slug='')
            )
            .select_related(
                'selected_variant',
                'selected_variant__product',
                'selected_variant__product__category',
                'product',
                'product__category',
            )
            .prefetch_related('selected_variant__images', 'product__images')
            .order_by('-created_at')
        )
        context['wishlist_items'] = list(wishlist_items)
        context['active_page'] = 'wishlist'
        try:
            cart = CartService.get_or_create_cart(self.request)
            cart_items = list(cart.items.filter(line_type=CartItem.LineKind.PURCHASE).values('product_id', 'selected_variant_id'))
            context['cart_variant_ids'] = set((i['selected_variant_id'] for i in cart_items if i['selected_variant_id']))
            context['cart_simple_product_ids'] = set((i['product_id'] for i in cart_items if not i['selected_variant_id']))
        except Exception:
            context['cart_variant_ids'] = set()
            context['cart_simple_product_ids'] = set()
        return context

def _redirect_open_cart():
    return redirect(reverse('store:home') + '?open_cart=1')


def _cart_stock_context(cart):
    issues = CartService.get_cart_stock_issues_for(cart)
    issue_map = {issue.item_id: issue for issue in issues}
    return {
        'cart_stock_issues': issues,
        'cart_stock_issue_map': issue_map,
        'checkout_blocked': bool(issues),
        'checkout_stock_summary': format_cart_stock_error(issues) if issues else '',
    }


def _checkout_items_queryset(cart):
    return cart.items.select_related(
        'product', 'combo', 'selected_variant', 'selected_pot',
    ).prefetch_related('combo__items__product', 'selected_variant__images', 'product__images')


def _checkout_guard_context(cart, addresses=None, active_address=None):
    """
    Stock guards + saved-address delivery map + resolved active state id.

    Active-state delivery issues/status come from resolve_checkout_totals (SSoT).
    """
    stock_ctx = _cart_stock_context(cart)
    items = list(_checkout_items_queryset(cart))
    state_id = None
    if active_address:
        state_id = resolve_delivery_state_id(
            delivery_state=active_address.delivery_state,
            state_text=active_address.state,
        )

    address_delivery = {}
    if addresses:
        for addr in addresses:
            addr_state_id = resolve_delivery_state_id(
                delivery_state=addr.delivery_state,
                state_text=addr.state,
            )
            # Expose on the instance for template data-state-id (legacy addresses
            # often have state text but a null delivery_state FK).
            addr.checkout_state_id = addr_state_id
            addr_issues = get_cart_delivery_issues(items, addr_state_id) if addr_state_id else []
            if addr_issues:
                names = ', '.join(issue.name for issue in addr_issues[:3])
                extra = f' (+{len(addr_issues) - 3} more)' if len(addr_issues) > 3 else ''
                addr_msg = (
                    f"{len(addr_issues)} item{'s' if len(addr_issues) != 1 else ''} "
                    f"can't be delivered here: {names}{extra}"
                )
            else:
                addr_msg = ''
            address_delivery[str(addr.pk)] = {
                'state_id': addr_state_id,
                'blocked': bool(addr_issues),
                'message': addr_msg,
                'issue_names': [issue.name for issue in addr_issues],
            }

    return {
        **stock_ctx,
        'checkout_address_delivery': address_delivery,
        'active_delivery_state_id': state_id,
    }


def _apply_checkout_totals_context(context, guard_ctx, checkout_totals):
    """Merge guard + resolve_checkout_totals into checkout template context (one path)."""
    context.update(guard_ctx)
    context['checkout_delivery_issues'] = checkout_totals.delivery_issues
    context['checkout_delivery_summary'] = checkout_totals.delivery_message
    context['checkout_shipping_label'] = checkout_totals.shipping_label
    context['checkout_delivery_status'] = checkout_totals.status
    context['checkout_blocked'] = bool(guard_ctx.get('checkout_blocked')) or checkout_totals.checkout_blocked
    stock_summary = guard_ctx.get('checkout_stock_summary') or ''
    context['checkout_summary'] = ' '.join(
        part for part in (stock_summary, checkout_totals.delivery_message) if part
    )
    return context


def _checkout_form_kwargs(request, cart, user, initial=None):
    items = list(_checkout_items_queryset(cart))
    kwargs = {
        'user': user,
        'cart_items': items,
    }
    if initial is not None:
        kwargs['initial'] = initial
    return kwargs


def _checkout_lines(cart, items, delivery_issues=None):
    issue_map = _cart_stock_context(cart)['cart_stock_issue_map']
    delivery_map = {issue.item_id: issue for issue in (delivery_issues or [])}
    return [
        {
            'item': item,
            'stock_issue': issue_map.get(item.id),
            'delivery_issue': delivery_map.get(item.id),
        }
        for item in items
    ]


class CartPageGoneRedirect(View):
    """Legacy /cart/ URLs: open side cart on home instead of a full cart page."""

    def get(self, request, *args, **kwargs):
        return _redirect_open_cart()


class AddToCartView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        form = CartAddForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Invalid cart data.')
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Invalid cart data.'}, status=400)
            product_id = request.POST.get('product_id')
            combo_id = request.POST.get('combo_id')
            if combo_id and Combo.objects.filter(pk=combo_id).exists():
                c = Combo.objects.get(pk=combo_id)
                return redirect('store:combo_detail', slug=c.slug)
            if product_id and Product.objects.filter(pk=product_id).exists():
                product = Product.objects.get(pk=product_id)
                return redirect('store:product_detail', slug=product.slug)
            return _redirect_open_cart()
        data = form.cleaned_data
        cart = CartService.get_or_create_cart(request)
        lt_raw = (data.get('line_type') or 'purchase').strip().lower()
        line_type = CartItem.LineKind.RENTAL if lt_raw == 'rental' else CartItem.LineKind.PURCHASE
        rb = data.get('rental_billing') or None
        ru = data.get('rental_period_count')
        rs_raw = (data.get('rental_start_date') or '').strip()
        re_raw = (data.get('rental_end_date') or '').strip()
        from django.utils.dateparse import parse_date
        rs = parse_date(rs_raw) if rs_raw else None
        re = parse_date(re_raw) if re_raw else None
        if data.get('combo_id'):
            combo = get_object_or_404(Combo, pk=data['combo_id'], is_active=True)
            try:
                CartService.add_combo_item(cart, combo, data['quantity'], line_type=line_type, is_gift=data.get('is_gift', False))
            except StockError as exc:
                messages.error(request, str(exc))
                if is_ajax:
                    return JsonResponse({'success': False, 'error': str(exc)}, status=400)
            except CartError as exc:
                messages.error(request, str(exc))
                if is_ajax:
                    return JsonResponse({'success': False, 'error': str(exc)}, status=400)
            else:
                if is_ajax:
                    cart_count = sum((item.quantity for item in cart.items.all()))
                    return JsonResponse({'success': True, 'cart_count': cart_count})
            action = request.POST.get('action', 'add')
            if action == 'buy':
                return redirect('store:checkout')
            return redirect(reverse('store:home') + '?open_cart=1&added=1')
        product = get_object_or_404(Product, pk=data['product_id'])
        sellable = None
        variant_id = data.get('variant_id')
        if variant_id:
            variant = Variant.objects.filter(product=product, pk=variant_id, is_active=True, stock_quantity__gt=0).select_related('product').first()
            if variant:
                sellable = variant
        if not sellable:
            if product.variants.exists():
                messages.error(request, 'Please select a variant (e.g. model/color) or selected variant is unavailable.')
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Please select a variant or selected variant is unavailable.'}, status=400)
                return redirect('store:product_detail', slug=product.slug)
            sellable = product
        try:
            CartService.add_item(cart, sellable, data['quantity'], line_type=line_type, rental_billing=rb, rental_units=ru, rental_start_date=rs, rental_end_date=re, is_gift=data.get('is_gift', False), selected_pot_id=data.get('selected_pot_id'))
        except StockError as exc:
            messages.error(request, str(exc))
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(exc)}, status=400)
        except CartError as exc:
            messages.error(request, str(exc))
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(exc)}, status=400)
        else:
            if is_ajax:
                cart_count = sum((item.quantity for item in cart.items.all()))
                return JsonResponse({'success': True, 'cart_count': cart_count})
        action = request.POST.get('action', 'add')
        if action == 'buy':
            return redirect('store:checkout')
        return redirect(reverse('store:home') + '?open_cart=1&added=1')

class BuyNowView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        form = CartAddForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Please select a variant and quantity.')
            product_id = request.POST.get('product_id')
            combo_id = request.POST.get('combo_id')
            if combo_id and Combo.objects.filter(pk=combo_id).exists():
                c = Combo.objects.get(pk=combo_id)
                return redirect('store:combo_detail', slug=c.slug)
            if product_id and Product.objects.filter(pk=product_id).exists():
                product = Product.objects.get(pk=product_id)
                return redirect('store:product_detail', slug=product.slug)
            return _redirect_open_cart()
        data = form.cleaned_data
        cart = CartService.get_or_create_cart(request)
        lt_raw = (data.get('line_type') or 'purchase').strip().lower()
        line_type = CartItem.LineKind.RENTAL if lt_raw == 'rental' else CartItem.LineKind.PURCHASE
        rb = data.get('rental_billing') or None
        ru = data.get('rental_period_count')
        rs_raw = (data.get('rental_start_date') or '').strip()
        re_raw = (data.get('rental_end_date') or '').strip()
        from django.utils.dateparse import parse_date
        rs = parse_date(rs_raw) if rs_raw else None
        re = parse_date(re_raw) if re_raw else None
        try:
            cart.items.all().delete()
            if data.get('combo_id'):
                combo = get_object_or_404(Combo, pk=data['combo_id'], is_active=True)
                CartService.add_combo_item(cart, combo, data['quantity'], line_type=line_type, is_gift=data.get('is_gift', False))
            else:
                product = get_object_or_404(Product, pk=data['product_id'])
                sellable = None
                variant_id = data.get('variant_id')
                if variant_id:
                    sellable = Variant.objects.filter(product=product, pk=variant_id, is_active=True, stock_quantity__gt=0).select_related('product').first()
                if not sellable:
                    if product.variants.exists():
                        messages.error(request, 'Please select a variant or the selected variant is unavailable.')
                        return redirect('store:product_detail', slug=product.slug)
                    sellable = product
                CartService.add_item(cart, sellable, data['quantity'], line_type=line_type, rental_billing=rb, rental_units=ru, rental_start_date=rs, rental_end_date=re, is_gift=data.get('is_gift', False), selected_pot_id=data.get('selected_pot_id'))
        except StockError as exc:
            messages.error(request, str(exc))
            if data.get('combo_id'):
                c = get_object_or_404(Combo, pk=data['combo_id'])
                return redirect('store:combo_detail', slug=c.slug)
            p = get_object_or_404(Product, pk=data['product_id'])
            return redirect('store:product_detail', slug=p.slug)
        except CartError as exc:
            messages.error(request, str(exc))
            if data.get('combo_id'):
                c = get_object_or_404(Combo, pk=data['combo_id'])
                return redirect('store:combo_detail', slug=c.slug)
            p = get_object_or_404(Product, pk=data['product_id'])
            return redirect('store:product_detail', slug=p.slug)
        return redirect('store:checkout')

class UpdateCartItemView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        form = CartUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Invalid update.')
            if is_ajax:
                return JsonResponse({'success': False}, status=400)
            return _redirect_open_cart()
        cart = CartService.get_or_create_cart(request)
        item = get_object_or_404(CartItem, pk=form.cleaned_data['item_id'], cart=cart)
        try:
            CartService.update_item(item, form.cleaned_data['quantity'])
        except StockError as exc:
            messages.error(request, str(exc))
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(exc)}, status=400)
            return _redirect_open_cart()
        if is_ajax:
            cart = CartService.get_or_create_cart(request)
            totals = CartService.compute_totals(cart)
            item_count = sum((line.quantity for line in cart.items.all()))
            return JsonResponse({'success': True, 'total': str(totals.subtotal), 'cart_count': item_count})
        return _redirect_open_cart()

class RemoveCartItemView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url and (not next_url.startswith('/')):
            next_url = None
        try:
            cart = CartService.get_or_create_cart(request)
            item = get_object_or_404(CartItem, pk=kwargs.get('item_id'), cart=cart)
            item.delete()
            is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
            if not is_ajax:
                messages.success(request, 'Item removed.')
        except Exception as e:
            logger.error('Error in RemoveCartItemView: %s', e, exc_info=True)
            is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Failed to remove item from cart.'}, status=400)
            messages.error(request, 'Failed to remove item from cart.')
        if next_url:
            return redirect(next_url)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if is_ajax:
            cart = CartService.get_or_create_cart(request)
            item_count = sum(item.quantity for item in cart.items.all())
            return JsonResponse({
                'success': True,
                'cart_count': item_count,
                'cart_empty': item_count == 0,
            })
        return _redirect_open_cart()

class CheckoutView(TemplateView):
    template_name = 'pages/checkout.html'

    def dispatch(self, request, *args, **kwargs):
        cart = CartService.get_or_create_cart(request)
        if not cart.items.exists():
            messages.info(request, 'Your cart is empty.')
            return _redirect_open_cart()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)
            cart = CartService.get_or_create_cart(self.request)
            user = self.request.user if self.request.user.is_authenticated else None
            addresses = []
            default_address = None
            initial = {}
            if user:
                from .models import Address
                addresses = list(
                    Address.objects.filter(user=user, is_snapshot=False)
                    .select_related('delivery_state')
                    .order_by('-is_default', '-created_at')
                )
                default_address = next((a for a in addresses if a.is_default), addresses[0] if addresses else None)
                payment_method = self.request.GET.get('payment')
                if payment_method in ('cod', 'razorpay'):
                    initial['payment'] = payment_method
                if default_address:
                    initial['selected_address'] = default_address.id
            else:
                payment_method = self.request.GET.get('payment')
                if payment_method in ('cod', 'razorpay'):
                    initial['payment'] = payment_method
            items = _checkout_items_queryset(cart)
            guard_ctx = _checkout_guard_context(cart, addresses=addresses, active_address=default_address)
            state_id = guard_ctx.get('active_delivery_state_id')
            checkout_totals = resolve_checkout_totals(cart, state_id=state_id, items=list(items))
            context.update({
                'captcha_site_key': settings.CAPTCHA_SITE_KEY,
                'cart': cart,
                'items': items,
                'checkout_lines': _checkout_lines(
                    cart,
                    items,
                    delivery_issues=checkout_totals.delivery_issues,
                ),
                'totals': checkout_totals.as_cart_totals(),
                'form': CheckoutForm(**_checkout_form_kwargs(self.request, cart, user, initial=initial)),
                'addresses': addresses,
                'default_address': default_address,
                'is_guest_checkout': user is None,
                'active_page': 'checkout',
            })
            return _apply_checkout_totals_context(context, guard_ctx, checkout_totals)
        except Exception as e:
            logger.error(f'Error in CheckoutView.get_context_data: {str(e)}', exc_info=True)
            user = self.request.user if self.request.user.is_authenticated else None
            context = super().get_context_data(**kwargs)
            context.update({'cart': None, 'items': [], 'totals': {'subtotal': 0, 'gst_total': 0, 'shipping': 0, 'total': 0}, 'form': CheckoutForm(user=user), 'addresses': [], 'default_address': None, 'is_guest_checkout': user is None, 'active_page': 'checkout', 'checkout_address_delivery': {}})
            return context

class OrderCreateView(FormView):
    form_class = CheckoutForm
    template_name = 'pages/checkout.html'

    def dispatch(self, request, *args, **kwargs):
        cart = CartService.get_or_create_cart(request)
        if not cart.items.exists():
            messages.info(request, 'Your cart is empty.')
            return _redirect_open_cart()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cart = CartService.get_or_create_cart(self.request)
        user = self.request.user if self.request.user.is_authenticated else None
        kwargs.update(_checkout_form_kwargs(self.request, cart, user))
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart = CartService.get_or_create_cart(self.request)
        user = self.request.user if self.request.user.is_authenticated else None
        addresses = []
        default_address = None
        if user:
            from .models import Address
            addresses = list(
                Address.objects.filter(user=user, is_snapshot=False)
                .select_related('delivery_state')
                .order_by('-is_default', '-created_at')
            )
            default_address = next((a for a in addresses if a.is_default), addresses[0] if addresses else None)
        items = _checkout_items_queryset(cart)
        guard_ctx = _checkout_guard_context(cart, addresses=addresses, active_address=default_address)
        checkout_totals = resolve_checkout_totals(
            cart,
            state_id=guard_ctx.get('active_delivery_state_id'),
            items=list(items),
        )
        context.update({
            'cart': cart,
            'items': items,
            'checkout_lines': _checkout_lines(
                cart,
                items,
                delivery_issues=checkout_totals.delivery_issues,
            ),
            'totals': checkout_totals.as_cart_totals(),
            'addresses': addresses,
            'default_address': default_address,
            'is_guest_checkout': user is None,
            'active_page': 'checkout',
        })
        return _apply_checkout_totals_context(context, guard_ctx, checkout_totals)

    def form_valid(self, form):
        try:
            if captcha_required():
                verify_captcha(extract_captcha_token(self.request), remote_ip=get_client_ip(self.request))
        except CaptchaError as exc:
            messages.error(self.request, str(exc))
            return redirect('store:checkout')
        cart = CartService.get_or_create_cart(self.request)
        payment_method = form.cleaned_data.get('payment')
        order_user = self.request.user if self.request.user.is_authenticated else None
        if payment_method == 'razorpay':
            messages.info(self.request, 'Please use the Pay & Place Order button for online payment.')
            return redirect('store:checkout')
        try:
            order = OrderService.create_order(cart, form.cleaned_data, user=order_user, clear_cart=True)
        except (CartError, StockError) as exc:
            messages.error(self.request, str(exc))
            return redirect(reverse('store:checkout') + '?stock_issue=1')
        send_order_confirmation_email_async(order)
        self.request.session['last_order_number'] = order.order_number
        return redirect('store:order_success', order_number=order.order_number)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

class CreateRazorpayOrderView(View):

    def post(self, request, *args, **kwargs):
        cart = CartService.get_or_create_cart(request)
        if not cart.items.exists():
            return JsonResponse({'status': 'error', 'message': 'Your cart is empty.'}, status=400)

        user = request.user if request.user.is_authenticated else None
        items = list(_checkout_items_queryset(cart))
        form = CheckoutForm(
            request.POST,
            user=user,
            cart_items=items,
        )
        if not form.is_valid():
            # TEMPORARY: log full errors to find root cause
            logger.error('CreateRazorpayOrderView form errors: %s', form.errors.as_json())
            msg = 'Please check your details.'
            for field in ('__all__', 'delivery_state', 'payment', 'full_name', 'phone', 'address_line', 'city', 'state', 'pincode', 'email'):
                errs = form.errors.get(field)
                if errs:
                    msg = errs[0] if isinstance(errs[0], str) else str(errs[0])
                    break
            return JsonResponse({'status': 'error', 'message': msg}, status=400)
        cleaned = form.cleaned_data
        if cleaned.get('payment') != 'razorpay':
            return JsonResponse({'status': 'error', 'message': 'Invalid payment method.'}, status=400)
        try:
            with transaction.atomic():
                items = list(
                    cart.items.select_related('selected_variant', 'product', 'combo', 'selected_pot')
                    .select_for_update(of=('self',)).all()
                )
                if not items:
                    return JsonResponse({'status': 'error', 'message': 'Cart is empty.'}, status=400)
                issues = get_cart_stock_issues(items)
                if issues:
                    return JsonResponse(
                        {'status': 'error', 'message': format_cart_stock_error(issues)},
                        status=400,
                    )
                order = OrderService.create_order(cart, cleaned, user=user, clear_cart=False)
                order.status = Order.Status.PLACED
                order.save(update_fields=['status'])
                session_checkout_data = {k: v for k, v in cleaned.items() if k != 'delivery_state'}
                if cleaned.get('delivery_state'):
                    session_checkout_data['delivery_state_id'] = cleaned['delivery_state'].pk
                request.session['pending_checkout_data'] = session_checkout_data
                request.session['last_order_number'] = order.order_number
                payment = order.payment
                client = razorpay.Client(auth=(settings.RZP_CLIENT_ID, settings.RZP_CLIENT_SECRET))
                amount_paise = int(order.total * 100)
                razorpay_order = client.order.create({'amount': amount_paise, 'currency': 'INR', 'payment_capture': 1})
                payment.razorpay_order_id = razorpay_order['id']
                payment.save(update_fields=['razorpay_order_id'])
            customer_email = order.address.email or '' if order.address else ''
            if user and (not customer_email):
                customer_email = getattr(user, 'email', '') or ''
            return JsonResponse({'status': 'success', 'razorpay_order_id': razorpay_order['id'], 'razorpay_key_id': settings.RZP_CLIENT_ID, 'amount': amount_paise, 'order_number': order.order_number, 'customer_name': order.address.full_name if order.address else '', 'customer_email': customer_email, 'customer_phone': order.address.phone if order.address else '', 'success_url': reverse('store:order_success', kwargs={'order_number': order.order_number})})
        except (CartError, StockError) as exc:
            return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)
        except Exception as e:
            logger.exception('CreateRazorpayOrderView error: %s', e)
            return JsonResponse({'status': 'error', 'message': 'Unable to create order. Please try again.'}, status=500)

class OrderSuccessView(DetailView):
    template_name = 'pages/success.html'
    context_object_name = 'order'
    slug_url_kwarg = 'order_number'
    slug_field = 'order_number'

    def get_queryset(self):
        return Order.objects.select_related('address', 'payment', 'shipment').prefetch_related('items')

    def dispatch(self, request, *args, **kwargs):
        try:
            order_number = kwargs.get('order_number')
            order = get_object_or_404(Order, order_number=order_number)
            if request.user.is_authenticated:
                if order.user and order.user != request.user:
                    return HttpResponseForbidden()
            elif request.session.get('last_order_number') != order_number:
                return HttpResponseForbidden()
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            logger.warning(f'Order not found: {order_number}')
            raise
        except Exception as e:
            logger.error(f'Error in OrderSuccessView.dispatch: {str(e)}', exc_info=True)
            messages.error(request, 'Failed to retrieve order details.')
            return redirect('store:home')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_page'] = 'orders'
        return context

class OrderDetailPageView(LoginRequiredMixin, DetailView):
    template_name = 'pages/order_detail.html'
    context_object_name = 'order'
    slug_url_kwarg = 'order_number'
    slug_field = 'order_number'

    def get_queryset(self):
        return (
            Order.objects.select_related('address', 'payment', 'shipment')
            .prefetch_related('items__product', 'items__combo', 'items__selected_variant')
            .filter(user=self.request.user)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_page'] = 'orders'
        return context

class OrderHistoryView(LoginRequiredMixin, ListView):
    template_name = 'pages/orders.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self):
        try:
            return Order.objects.filter(user=self.request.user).select_related('address').prefetch_related('items')
        except Exception as e:
            logger.error(f'Error in OrderHistoryView.get_queryset: {str(e)}', exc_info=True)
            return Order.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_page'] = 'orders'
        return context

class ContactView(FormView):
    template_name = 'pages/contact.html'
    form_class = ContactForm
    success_url = reverse_lazy('store:contact')

    def form_valid(self, form):
        try:
            if captcha_required():
                verify_captcha(extract_captcha_token(self.request), remote_ip=get_client_ip(self.request))
        except CaptchaError as exc:
            messages.error(self.request, str(exc))
            return self.form_invalid(form)
        try:
            form.save()
            messages.success(self.request, 'Thanks for reaching out! We will respond soon.')
        except Exception as e:
            logger.error(f'Error in ContactView.form_valid: {str(e)}', exc_info=True)
            messages.error(self.request, 'Failed to save your message. Please try again.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_page'] = 'contact'
        context['captcha_site_key'] = settings.CAPTCHA_SITE_KEY
        return context

class StaticPageView(TemplateView):
    template_name = 'pages/about.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.extra_context and 'active_page' in self.extra_context:
            context['active_page'] = self.extra_context['active_page']
        return context

class NewsletterSubscribeView(FormView):
    form_class = NewsletterForm
    success_url = reverse_lazy('store:home')

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER', str(self.success_url))

    def form_valid(self, form):
        try:
            email = form.cleaned_data['email'].lower()
            subscription, created = form._meta.model.objects.get_or_create(email=email)
            if not created and (not subscription.is_active):
                subscription.is_active = True
                subscription.save(update_fields=['is_active'])
            messages.success(self.request, 'Thanks for subscribing!')
        except Exception as e:
            logger.error(f'Error in NewsletterSubscribeView.form_valid: {str(e)}', exc_info=True)
            messages.error(self.request, 'Failed to subscribe. Please try again.')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Please enter a valid email.')
        return redirect(self.get_success_url())

class RazorpayPaymentVerifyView(View):

    def post(self, request, *args, **kwargs):
        try:
            razorpay_order_id = request.POST.get('razorpay_order_id')
            razorpay_payment_id = request.POST.get('razorpay_payment_id')
            razorpay_signature = request.POST.get('razorpay_signature')
            if not (razorpay_order_id and razorpay_payment_id and razorpay_signature):
                try:
                    data = json.loads(request.body or '{}')
                except (TypeError, ValueError, json.JSONDecodeError):
                    data = {}
                razorpay_order_id = razorpay_order_id or data.get('razorpay_order_id')
                razorpay_payment_id = razorpay_payment_id or data.get('razorpay_payment_id')
                razorpay_signature = razorpay_signature or data.get('razorpay_signature')
            if not (razorpay_order_id and razorpay_payment_id and razorpay_signature):
                return JsonResponse({'status': 'error', 'message': 'Missing payment parameters.', 'redirect': '/?open_cart=1'}, status=400)
            logger.info('Payment verification attempt - Order: %s, Payment: %s', razorpay_order_id, razorpay_payment_id)
            payment = Payment.objects.select_related('order').get(razorpay_order_id=razorpay_order_id)
            if payment.status == Payment.Status.PAID:
                return JsonResponse({'status': 'success', 'message': 'Payment already verified', 'order_number': payment.order.order_number, 'redirect': reverse('store:order_success', kwargs={'order_number': payment.order.order_number})})
            signature_data = f'{razorpay_order_id}|{razorpay_payment_id}'
            signature_check = hmac.new(settings.RZP_CLIENT_SECRET.encode(), signature_data.encode(), hashlib.sha256).hexdigest()
            if signature_check == razorpay_signature:
                payment.razorpay_payment_id = razorpay_payment_id
                payment.razorpay_signature = razorpay_signature
                payment.status = Payment.Status.PAID
                payment.processed_at = timezone.now()
                payment.save(update_fields=['status', 'processed_at', 'razorpay_payment_id', 'razorpay_signature'])
                order = payment.order
                old_status = order.status
                order.status = Order.Status.CONFIRMED
                order.save(update_fields=['status'])
                for item in order.items.select_related('product', 'selected_variant', 'combo').prefetch_related('product__combo_components', 'combo__items').all():
                    if item.combo_id:
                        for row in item.combo.items.all():
                            dec = item.quantity * int(row.quantity or 1)
                            Product.objects.filter(pk=row.product_id).update(base_stock=F('base_stock') - dec)
                        continue
                    product = item.product
                    if getattr(product, 'is_combo_product', False):
                        for row in product.combo_components.all():
                            dec = item.quantity * row.quantity
                            Product.objects.filter(pk=row.component_product_id).update(base_stock=F('base_stock') - dec)
                    elif item.selected_variant_id:
                        Variant.objects.filter(pk=item.selected_variant_id).update(stock_quantity=F('stock_quantity') - item.quantity)
                    else:
                        Product.objects.filter(pk=product.pk).update(base_stock=F('base_stock') - item.quantity)
                cart = CartService.get_or_create_cart(request)
                if cart.items.exists():
                    for cart_item in cart.items.select_related('selected_pot').all():
                        if cart_item.selected_pot_id:
                            Product.objects.filter(pk=cart_item.selected_pot_id).update(
                                base_stock=F('base_stock') - cart_item.quantity
                            )
                    cart.status = Cart.Status.ORDERED
                    cart.save(update_fields=['status'])
                    cart.items.all().delete()
                if 'pending_checkout_data' in request.session:
                    del request.session['pending_checkout_data']
                try:
                    if order.status == Order.Status.CONFIRMED and order.status != old_status:
                        send_order_confirmation_email_async(order)
                except Exception:
                    pass
                return JsonResponse({'status': 'success', 'message': 'Payment verified successfully', 'order_number': payment.order.order_number, 'redirect': reverse('store:order_success', kwargs={'order_number': payment.order.order_number})})
            else:
                payment.status = Payment.Status.FAILED
                payment.save(update_fields=['status'])
                order = payment.order
                order_number = order.order_number
                order.delete()
                if 'pending_checkout_data' in request.session:
                    del request.session['pending_checkout_data']
                return JsonResponse({'status': 'error', 'message': 'Payment verification failed. Please try again.', 'redirect': '/?open_cart=1'}, status=400)
        except Payment.DoesNotExist:
            if 'pending_checkout_data' in request.session:
                del request.session['pending_checkout_data']
            return JsonResponse({'status': 'error', 'message': 'Payment record not found', 'redirect': '/?open_cart=1'}, status=404)
        except Exception as e:
            if 'pending_checkout_data' in request.session:
                del request.session['pending_checkout_data']
            return JsonResponse({'status': 'error', 'message': f'Payment verification error: {str(e)}', 'redirect': '/?open_cart=1'}, status=500)

class RazorpayPaymentCancelView(View):

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            order_number = data.get('order_number')
            order = Order.objects.select_related('user', 'address').get(order_number=order_number)
            if request.user.is_authenticated:
                if order.user_id != request.user.id:
                    return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            elif request.session.get('last_order_number') != order_number:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
            try:
                payment = order.payment
            except Payment.DoesNotExist:
                payment = None
            order.delete()
            if 'pending_checkout_data' in request.session:
                del request.session['pending_checkout_data']
            return JsonResponse({'status': 'success', 'message': 'Payment cancelled. Your order has been cancelled.', 'redirect': '/?open_cart=1'})
        except Order.DoesNotExist:
            logger.warning('Order not found for cancellation: %s', order_number)
            if 'pending_checkout_data' in request.session:
                del request.session['pending_checkout_data']
            return JsonResponse({'status': 'success', 'message': 'Returning to cart...', 'redirect': '/?open_cart=1'})
        except Exception as e:
            if 'pending_checkout_data' in request.session:
                del request.session['pending_checkout_data']
            return JsonResponse({'status': 'success', 'message': 'Returning to cart...', 'redirect': '/?open_cart=1'})

class CartDrawerView(View):

    def get(self, request, *args, **kwargs):
        try:
            cart = CartService.get_or_create_cart(request)
            items_qs = cart.items.select_related('product', 'combo', 'selected_variant').prefetch_related('selected_variant__images', 'combo__items__product').all()
            items_data = []
            for item in items_qs:
                image_url = None
                if item.combo_id:
                    try:
                        raw = item.get_display_image_url()
                        if raw:
                            image_url = request.build_absolute_uri(raw) if raw.startswith('/') else raw
                    except Exception:
                        pass
                    variant_display = item.variant_display or 'Bundle'
                    unit_price = item.unit_price
                    product_url = request.build_absolute_uri(reverse('store:combo_detail', kwargs={'slug': item.combo.slug}))
                    items_data.append({'id': item.id, 'name': item.combo.name, 'variant_display': variant_display, 'unit_price': str(unit_price or 0), 'quantity': item.quantity, 'image': image_url or '', 'product_url': product_url})
                    continue
                if item.selected_variant:
                    for img in item.selected_variant.images.filter(image__isnull=False).exclude(image='').order_by('-is_primary', 'display_order', 'id'):
                        try:
                            raw = img.image.url
                            if raw:
                                image_url = request.build_absolute_uri(raw) if raw.startswith('/') else raw
                                break
                        except Exception:
                            pass
                else:
                    try:
                        card_images = item.product.get_card_image_urls(limit=1)
                        if card_images:
                            url = card_images[0]
                            image_url = request.build_absolute_uri(url) if url.startswith('/') else url
                    except Exception:
                        pass
                variant_display = ''
                try:
                    variant_display = item.variant_display or ''
                except Exception:
                    if item.selected_variant:
                        try:
                            variant_display = item.selected_variant.get_attribute_values_display()
                        except Exception:
                            pass
                unit_price = item.unit_price
                if item.product and item.selected_variant_id:
                    product_url = request.build_absolute_uri(f'/products/{item.product.slug}/?variant={item.selected_variant_id}')
                elif item.product:
                    product_url = request.build_absolute_uri(f'/products/{item.product.slug}/')
                else:
                    product_url = request.build_absolute_uri('/products/')
                items_data.append({'id': item.id, 'name': item.product.name if item.product else '', 'variant_display': variant_display, 'unit_price': str(unit_price or 0), 'quantity': item.quantity, 'image': image_url or '', 'product_url': product_url})
            totals = CartService.compute_totals(cart)
            item_count = sum((i['quantity'] for i in items_data))
            return JsonResponse({'success': True, 'items': items_data, 'total': str(totals.subtotal), 'subtotal': str(totals.subtotal), 'item_count': item_count})
        except Exception as exc:
            logger.error('CartDrawerView error: %s', exc, exc_info=True)
            return JsonResponse({'success': False, 'items': [], 'total': '0', 'subtotal': '0', 'item_count': 0})


class CheckoutTotalsView(View):
    """
    Recalculate checkout totals for a delivery state.

    GET /api/checkout/totals/?state_id=5
    """

    def get(self, request, *args, **kwargs):
        cart = CartService.get_or_create_cart(request)
        items = list(_checkout_items_queryset(cart))
        raw_state = request.GET.get('state_id') or ''
        state_id = resolve_delivery_state_id(delivery_state=raw_state) if raw_state else None
        result = resolve_checkout_totals(cart, state_id=state_id, items=items)
        return JsonResponse(result.to_api_dict(items))
