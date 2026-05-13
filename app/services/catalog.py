from django.db.models import OuterRef, Subquery, Q
from ..models import Combo, Variant
from .category_tree import category_filter_ids_for_slug
from .combo_catalog import combo_is_in_stock, prefetch_combo_items

def active_variant_qs():
    """
    All sellable variants with their product + images.
    Used by API views (RecentlyViewed, NewArrivals, etc.) — unchanged.
    """
    return (
        Variant.objects.filter(
            is_active=True,
            product__is_active=True,
            stock_quantity__gt=0,
        )
        .select_related('product', 'product__category', 'product__rental_config')
        .prefetch_related('images')
    )
 
 
# ─────────────────────────────────────────────
# Plant-filter helpers — unchanged
# ─────────────────────────────────────────────
 
def apply_plant_filters_to_variant_qs(qs, request):
    difficulty = (request.GET.get('difficulty') or '').strip().lower()
    if difficulty in ('easy', 'medium', 'hard'):
        qs = qs.filter(product__difficulty=difficulty)
    sunlight = (request.GET.get('sunlight') or '').strip().lower()
    if sunlight in ('full_sun', 'partial', 'low_light'):
        qs = qs.filter(product__sunlight=sunlight)
    watering = (request.GET.get('watering') or '').strip().lower()
    if watering in ('low', 'medium', 'high'):
        qs = qs.filter(product__watering=watering)
    plant_type = (request.GET.get('plant_type') or '').strip().lower()
    if plant_type in ('indoor', 'outdoor', 'flowering'):
        qs = qs.filter(product__plant_type=plant_type)
    guide = (request.GET.get('guide') or '').strip().lower()
    if guide == 'beginner':
        qs = qs.filter(product__beginner_friendly=True)
    elif guide == 'low_maintenance':
        qs = qs.filter(product__low_maintenance=True)
    elif guide == 'air_purifying':
        qs = qs.filter(product__air_purifying=True)
    elif guide == 'office':
        qs = qs.filter(product__office_friendly=True)
    return qs
 
def apply_plant_filters_to_product_qs(qs, request):
    difficulty = (request.GET.get('difficulty') or '').strip().lower()
    if difficulty in ('easy', 'medium', 'hard'):
        qs = qs.filter(difficulty=difficulty)
    sunlight = (request.GET.get('sunlight') or '').strip().lower()
    if sunlight in ('full_sun', 'partial', 'low_light'):
        qs = qs.filter(sunlight=sunlight)
    watering = (request.GET.get('watering') or '').strip().lower()
    if watering in ('low', 'medium', 'high'):
        qs = qs.filter(watering=watering)
    plant_type = (request.GET.get('plant_type') or '').strip().lower()
    if plant_type in ('indoor', 'outdoor', 'flowering'):
        qs = qs.filter(plant_type=plant_type)
    guide = (request.GET.get('guide') or '').strip().lower()
    if guide == 'beginner':
        qs = qs.filter(beginner_friendly=True)
    elif guide == 'low_maintenance':
        qs = qs.filter(low_maintenance=True)
    elif guide == 'air_purifying':
        qs = qs.filter(air_purifying=True)
    elif guide == 'office':
        qs = qs.filter(office_friendly=True)
    return qs
 
 
# ─────────────────────────────────────────────
# Combo cards — unchanged
# ─────────────────────────────────────────────
 
def collection_combo_cards(request):
    """Active purchasable combos with stock; respects price, search, sort."""
    qs = (
        Combo.objects.filter(is_active=True, purchase_enabled=True)
        .prefetch_related(prefetch_combo_items())
    )
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    query = request.GET.get('q')
    sort = (request.GET.get('sort') or '').strip().lower()
    if min_price:
        qs = qs.filter(price__gte=min_price)
    if max_price:
        qs = qs.filter(price__lte=max_price)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if sort == 'price_asc':
        qs = qs.order_by('price', '-updated_at')
    elif sort == 'price_desc':
        qs = qs.order_by('-price', '-updated_at')
    else:
        qs = qs.order_by('-updated_at', '-id')
    cards = []
    for c in qs:
        if c.price and combo_is_in_stock(c, multiplier=1):
            cards.append({'kind': 'combo', 'combo': c})
    return cards
 
 
# ─────────────────────────────────────────────
# OPTIMIZED: collection_card_items
# ─────────────────────────────────────────────
 
def collection_card_items(request, paginate_by=12):
    """
    Returns one card-dict per product (cheapest in-stock variant chosen).
 
    BEFORE: fetched ALL variants into Python, deduped with a seen-set.
            At 5 000 variants that's 5 000 ORM rows deserialized every request.
 
    AFTER:  subquery picks the lowest-price active variant id per product
            entirely inside the DB.  Python only sees one row per product.
 
    Steps
    ─────
    1. Build a filtered base queryset of Variant rows (same filters as before).
    2. Use a correlated Subquery to find the MIN-price variant id per product_id.
    3. Filter the base qs to only those "winner" variant ids.
    4. fetch_related images in one extra query (prefetch_related).
    Result: 2 DB queries total instead of 1 huge scan + Python loop.
    """
    _ = paginate_by  # kept for API compatibility
 
    category   = request.GET.get('category')
    min_price  = request.GET.get('min_price')
    max_price  = request.GET.get('max_price')
    query      = request.GET.get('q')
    sort       = (request.GET.get('sort') or '').strip().lower()
    rent_only  = (request.GET.get('rent') or '').strip() in ('1', 'true', 'yes')
 
    # ── Step 1: build the filtered base qs (no select_related yet — keep it cheap) ──
    base_qs = Variant.objects.filter(
        is_active=True,
        product__is_active=True,
        stock_quantity__gt=0,
    )
 
    if rent_only:
        base_qs = base_qs.filter(
            product__is_rent_available=True,
            product__rental_config__is_rent_enabled=True,
        )
 
    if category and category != 'all':
        _, ids = category_filter_ids_for_slug(category, include_children=True, max_depth=10)
        if ids:
            base_qs = base_qs.filter(product__category_id__in=ids)
 
    if min_price:
        base_qs = base_qs.filter(price__gte=min_price)
    if max_price:
        base_qs = base_qs.filter(price__lte=max_price)
 
    if query:
        base_qs = base_qs.filter(
            Q(product__name__icontains=query)
            | Q(product__description__icontains=query)
            | Q(product__category__name__icontains=query)
        )
 
    base_qs = apply_plant_filters_to_variant_qs(base_qs, request)
 
    # ── Step 2: determine ordering ──
    if sort == 'price_asc':
        order_fields = ('price', '-product__created_at')
        subquery_order = 'price'           # cheapest variant wins
    elif sort == 'price_desc':
        order_fields = ('-price', '-product__created_at')
        subquery_order = '-price'          # most expensive variant wins
    else:
        # Default: newest product first, then lowest display_order variant
        order_fields = ('-product__created_at', '-product__id')
        subquery_order = 'display_order'
 
    # ── Step 3: correlated subquery — one winner variant id per product ──
    # "For each product_id that appears in base_qs, give me the id of the
    #  variant with the best sort position."
    winner_subquery = (
        base_qs.filter(product_id=OuterRef('product_id'))
        .order_by(subquery_order, 'id')
        .values('id')[:1]
    )
 
    # ── Step 4: final qs — only winner rows, fully hydrated ──
    winner_qs = (
        base_qs
        .annotate(winner_id=Subquery(winner_subquery))
        .filter(id=Subquery(winner_subquery))   # keep only the chosen variant per product
        .select_related('product', 'product__category', 'product__rental_config')
        .prefetch_related('images')
        .order_by(*order_fields)
    )
 
    cards = [
        {'kind': 'variant', 'variant': v, 'is_jewellery': False}
        for v in winner_qs
    ]
    return cards
