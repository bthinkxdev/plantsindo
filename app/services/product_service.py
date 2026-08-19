"""Product detail (PDP) data loading and context building – optimized querysets, no template logic."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Count, Prefetch
from django.urls import reverse

from app.models import (
    CartItem,
    Order,
    OrderItem,
    Product,
    ProductComboItem,
    ProductFAQ,
    ProductHighlight,
    ProductPotAddon,
    ProductSpecification,
    ProductWhatsInBoxItem,
    Review,
    Variant,
    Wishlist,
)
from app.services import CartService
from app.services.pincode import allowed_pincode_list
from app.services.rental_catalog import combo_is_in_stock
from app.services.rental_pricing import rental_key as make_rental_key


def get_pdp_queryset():
    """queryset for ProductDetailView with prefetch to avoid N+1 on gallery, variants, and content modules."""
    combo_pf = Prefetch(
        'combo_components',
        queryset=ProductComboItem.objects.select_related('component_product').order_by('display_order', 'id'),
    )
    variant_pf = Prefetch(
        'variants',
        queryset=Variant.objects.filter(is_active=True, stock_quantity__gt=0)
        .prefetch_related('images', 'attribute_values__attribute')
        .order_by('display_order', 'id'),
    )
    return (
        Product.objects.active()
        .select_related('category', 'extended_content')
        .prefetch_related(
            'attributes__values',
            'images',
            combo_pf,
            variant_pf,
            Prefetch('highlights', queryset=ProductHighlight.objects.all().order_by('display_order', 'id')),
            Prefetch('whats_in_box_items', queryset=ProductWhatsInBoxItem.objects.all().order_by('display_order', 'id')),
            Prefetch('specifications', queryset=ProductSpecification.objects.all().order_by('display_order', 'id')),
            Prefetch('faqs', queryset=ProductFAQ.objects.all().order_by('display_order', 'id')),
        )
    )


def resolve_variants_for_detail(product: Product, request) -> Tuple[List[Variant], Optional[Variant]]:
    variants = list(
        product.variants.filter(is_active=True)
        .prefetch_related('attribute_values__attribute', 'images')
        .order_by('display_order', 'id')
    )
    selected_variant = None
    variant_param = request.GET.get('variant')
    if variant_param:
        try:
            vid = int(variant_param)
        except (TypeError, ValueError):
            vid = None
        if vid:
            for v in variants:
                if v.id == vid:
                    selected_variant = v
                    break
    if not selected_variant and variants:
        in_stock = [v for v in variants if getattr(v, 'stock_quantity', 0) > 0]
        selected_variant = in_stock[0] if in_stock else variants[0]
    return variants, selected_variant


def build_attributes_grouped(product: Product, variants: List[Variant]) -> List[Dict[str, Any]]:
    used_value_ids = set()
    for v in variants:
        for av in v.attribute_values.all():
            used_value_ids.add(av.id)
    attributes_grouped = []
    for attr in product.attributes.prefetch_related('values').order_by('display_order', 'name'):
        sorted_values = sorted(attr.values.all(), key=lambda av: (av.display_order, av.value, av.id))
        values_for_attr = [
            {'id': av.id, 'value': av.value}
            for av in sorted_values
            if av.id in used_value_ids
        ]
        if not values_for_attr:
            continue
        attributes_grouped.append({'id': attr.id, 'name': attr.name, 'values': values_for_attr})
    return attributes_grouped


def _variant_json_payload(product: Product, variants: List[Variant]) -> List[Dict[str, Any]]:
    variant_json = []
    for v in variants:
        attr_map = {}
        for av in v.attribute_values.select_related('attribute').all():
            attr = getattr(av, 'attribute', None)
            if not attr or not attr.name:
                continue
            attr_map[attr.name] = av.value
        imgs = list(v.images.filter(image__isnull=False).exclude(image='').order_by('-is_primary', 'display_order', 'id'))
        primary_image_url = None
        for img in imgs:
            try:
                if img.image and img.image.url:
                    primary_image_url = img.image.url
                    break
            except Exception:
                continue
        variant_json.append(
            {
                'id': v.id,
                'price': str(v.price),
                'original_price': str(v.original_price) if v.original_price else '',
                'discount_percent': v.discount_percent,
                'stock': v.stock_quantity,
                'stock_quantity': v.stock_quantity,
                'attributes': attr_map,
                'attribute_value_ids': list(v.attribute_values.order_by('id').values_list('id', flat=True)),
                'image': primary_image_url,
                'is_gst_applicable': bool(product.is_gst_applicable),
                'gst_percentage': str(product.gst_percentage) if product.is_gst_applicable and product.gst_percentage is not None else None,
            }
        )
    return variant_json


def _load_pot_addons(product: Product) -> List[Dict[str, Any]]:
    """
    Load pot addons for a plant product.
    Returns a list of dicts ready for the template and JSON serialization.
    Silently returns [] if the product has no addons or anything goes wrong.
    """
    try:
        rows = (
            ProductPotAddon.objects
            .filter(plant_product=product)
            .select_related('pot_product', 'pot_product__category')
            .prefetch_related('pot_product__images')
            .order_by('display_order', 'id')
        )
        addons = []
        for row in rows:
            pot = row.pot_product
            if not pot.is_active:
                continue
            price = pot.base_price
            if price is None or price <= 0:
                continue
            stock = pot.base_stock or 0
            image_url = None
            try:
                urls = pot.get_card_image_urls(limit=1)
                image_url = urls[0] if urls else None
            except Exception:
                pass
            addons.append({
                'id': pot.id,
                'name': pot.name,
                'price': price,
                'stock': stock,
                'in_stock': stock > 0,
                'image_url': image_url,
                'slug': pot.slug,
            })
        return addons
    except Exception as e:
        import logging
        logging.getLogger(__name__).error('Error loading pot addons for product %s: %s', product.pk, e)
        return []


class ProductDetailService:
    """Builds PDP context dictionaries – used by DetailView and lazy fragment views."""

    @staticmethod
    def build_breadcrumbs(product: Product) -> List[Dict[str, str]]:
        items = [
            {'label': 'Home', 'url': reverse('store:home')},
            {'label': 'Shop', 'url': reverse('store:product_list')},
        ]
        cat = product.category
        if cat:
            ancestors = []
            cur = cat
            depth = 0
            seen = set()
            while cur is not None and depth < 15:
                if cur.pk and cur.pk in seen:
                    break
                if cur.pk:
                    seen.add(cur.pk)
                ancestors.append(cur)
                cur = getattr(cur, 'parent', None)
                depth += 1
            for ancestor in reversed(ancestors):
                items.append({
                    'label': ancestor.name,
                    'url': f"{reverse('store:product_list')}?category={ancestor.slug}",
                })
        items.append({'label': product.name, 'url': ''})
        return items

    @staticmethod
    def build_reviews_context(request, product: Product) -> Dict[str, Any]:
        reviews_qs = (
            Review.objects
            .filter(product=product, is_approved=True, is_deleted=False)
            .select_related('user', 'order')
            .order_by('-created_at')
        )
        reviews_list = list(reviews_qs[:250])
        total_reviews = product.total_reviews or 0
        average_rating = float(product.average_rating) if total_reviews > 0 else None
        breakdown_raw = reviews_qs.values('rating').annotate(count=Count('id'))
        rating_breakdown = {i: 0 for i in range(5, 0, -1)}
        for row in breakdown_raw:
            r = int(row['rating'])
            if 1 <= r <= 5:
                rating_breakdown[r] = row['count']
        breakdown_rows = []
        for star in range(5, 0, -1):
            count = rating_breakdown.get(star, 0)
            percent = int(count / total_reviews * 100) if total_reviews else 0
            breakdown_rows.append({'star': star, 'count': count, 'percent': percent})
        can_review = False
        user_review = None
        if request.user.is_authenticated:
            user_review = Review.objects.filter(product=product, user=request.user).first()
            if not user_review:
                has_delivered_order = OrderItem.objects.filter(
                    order__user=request.user,
                    order__status=Order.Status.DELIVERED,
                    product=product,
                ).exists()
                can_review = has_delivered_order
        from app.forms import ReviewForm
        return {
            'product': product,
            'reviews': reviews_list,
            'average_rating': average_rating,
            'total_reviews': total_reviews,
            'rating_breakdown': rating_breakdown,
            'rating_breakdown_rows': breakdown_rows,
            'can_review': can_review,
            'user_review': user_review,
            'review_form': ReviewForm(),
        }

    @staticmethod
    def augment_context(request, product: Product) -> Dict[str, Any]:
        variants, selected_variant = resolve_variants_for_detail(product, request)
        attributes_grouped = build_attributes_grouped(product, variants)
        context: Dict[str, Any] = {
            'variants': variants,
            'selected_variant': selected_variant,
            'attributes_grouped': attributes_grouped,
            'pdp_breadcrumbs': ProductDetailService.build_breadcrumbs(product),
        }

        if product.is_simple_product():
            context['product_display_image_urls'] = product.get_card_image_urls(limit=3)
        else:
            context['product_display_image_urls'] = []

        context['ordered_attributes'] = [a['name'] for a in attributes_grouped]
        context['variant_json'] = _variant_json_payload(product, variants)

        if product.is_simple_product():
            context['product_base_original_price'] = product.base_original_price
            context['product_discount_percent'] = product.discount_percent
        else:
            context['product_base_original_price'] = None
            context['product_discount_percent'] = 0

        base_price_for_gst = None
        if selected_variant:
            base_price_for_gst = selected_variant.price
        elif product.is_simple_product() and product.base_price is not None:
            base_price_for_gst = product.base_price

        if (
            base_price_for_gst is not None
            and getattr(product, 'is_gst_applicable', False)
            and getattr(product, 'gst_percentage', None) is not None
        ):
            gst_pct = product.gst_percentage
            gst_amount = base_price_for_gst * (gst_pct / Decimal('100'))
            context['product_detail_gst_amount'] = gst_amount
            context['product_detail_total_with_gst'] = base_price_for_gst + gst_amount
            context['product_gst_percentage'] = gst_pct
        else:
            context['product_detail_gst_amount'] = None
            context['product_detail_total_with_gst'] = None
            context['product_gst_percentage'] = None

        selected_attr_value_ids = []
        if selected_variant:
            selected_attr_value_ids = list(selected_variant.attribute_values.values_list('id', flat=True))
        context['selected_attribute_value_ids'] = selected_attr_value_ids

        context['in_wishlist'] = False
        if request.user.is_authenticated and selected_variant:
            context['in_wishlist'] = Wishlist.objects.filter(
                user=request.user, selected_variant=selected_variant
            ).exists()
        elif request.user.is_authenticated and product.is_simple_product():
            context['in_wishlist'] = Wishlist.objects.filter(
                user=request.user, product=product
            ).exists()

        context['related_products'] = list(
            Product.objects.active()
            .filter(category=product.category)
            .exclude(pk=product.pk)
            .select_related('category')
            .prefetch_related('variants__images', 'images')[:4]
        )
        context['similar_variants'] = [
            v for v in variants if selected_variant and v.id != selected_variant.id
        ][:12]

        combo_lines = []
        if getattr(product, 'is_combo_product', False):
            for row in product.combo_components.all():
                combo_lines.append({'name': row.component_product.name, 'quantity': row.quantity})
        context['combo_lines'] = combo_lines

        if getattr(product, 'is_rent_available', False):
            context['product_rental_options'] = [{'billing': 'day', 'units': 1, 'key': make_rental_key(1)}]
        else:
            context['product_rental_options'] = []

        context['show_pdp_mode_toggle'] = bool(product.purchase_enabled and product.is_rent_available)
        context['rental_only_pdp'] = bool(product.is_rent_available and not product.purchase_enabled)
        context['purchase_only_pdp'] = bool(product.purchase_enabled and not product.is_rent_available)

        cart = CartService.get_or_create_cart(request)
        if selected_variant:
            pq = cart.items.filter(product=product, selected_variant_id=selected_variant.id)
        else:
            pq = cart.items.filter(product=product, selected_variant__isnull=True)
        context['pdp_purchase_in_cart'] = pq.filter(line_type=CartItem.LineKind.PURCHASE).exists()
        context['pdp_rental_keys_in_cart'] = list(
            pq.filter(line_type=CartItem.LineKind.RENTAL).values_list('rental_key', flat=True)
        )

        context['pincode_check_url'] = reverse('store:pincode_check')
        context['serviceable_pincode_count'] = len(allowed_pincode_list())
        context['pdp_combo_available'] = (
            combo_is_in_stock(product, multiplier=1)
            if getattr(product, 'is_combo_product', False)
            else True
        )

        cfg = getattr(product, 'rental_config', None)
        context['product_rental_rates'] = {
            'day': str(cfg.rent_price_per_day) if cfg and cfg.rent_price_per_day is not None else '',
        }

        from app.forms import CartAddForm
        context['add_form'] = CartAddForm(initial={
            'product_id': product.id,
            'variant_id': selected_variant.id if selected_variant else None,
            'quantity': 1,
            'line_type': 'purchase',
        })

        context['active_page'] = 'collection'
        context['selected_color_variant'] = selected_variant

        total_reviews = product.total_reviews or 0
        context['average_rating'] = float(product.average_rating) if total_reviews > 0 else None
        context['total_reviews'] = total_reviews
        context['reviews'] = []
        context['pdp_reviews_lazy'] = True
        context['pdp_reviews_url'] = reverse('store:pdp_reviews_fragment', kwargs={'slug': product.slug})
        context['pdp_seo_url'] = reverse('store:pdp_seo_fragment', kwargs={'slug': product.slug})
        context['rating_breakdown'] = {}
        context['rating_breakdown_rows'] = []
        context['can_review'] = False
        context['user_review'] = None
        context['review_form'] = None

        # ── Pot add-ons ────────────────────────────────────────────────────────
        pot_addons = _load_pot_addons(product)
        context['pot_addons'] = pot_addons
        context['pot_addons_json'] = json.dumps([
            {
                'id': p['id'],
                'name': p['name'],
                'price': str(p['price']),
                'in_stock': p['in_stock'],
                'image_url': p['image_url'] or '',
            }
            for p in pot_addons
        ])

        return context
