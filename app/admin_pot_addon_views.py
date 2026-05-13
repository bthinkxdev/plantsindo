import json
import logging
from django.db import IntegrityError
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View
 
from .models import Product, ProductPotAddon
 
logger = logging.getLogger(__name__)
 
 
def _pot_category_ids():
    """
    Return PKs of all categories whose slug is 'pot' or 'pots' (case-insensitive).
    Returns an empty list if none found — caller should handle gracefully.
    """
    from .models import Category
    return list(
        Category.objects.filter(
            slug__in=['pot', 'pots'],
            is_active=True,
        ).values_list('id', flat=True)
    )
 
 
def _pot_product_qs():
    """
    Base queryset for pot products:
    - Active products
    - Under a pot category (slug 'pot' or 'pots')
    - Simple products only (no variants needed — pot price is base_price)
    """
    cat_ids = _pot_category_ids()
    if not cat_ids:
        return Product.objects.none()
    return (
        Product.objects.filter(
            is_active=True,
            category_id__in=cat_ids,
        )
        .select_related('category')
        .order_by('name')
    )
 
 
class ProductPotAddonsListApiView(View):
    """
    GET /admin/products/<pk>/pot-addons/
    Returns all pot addons currently linked to this plant product.
    """
 
    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        rows = (
            product.pot_addons
            .select_related('pot_product', 'pot_product__category')
            .order_by('display_order', 'id')
        )
        data = []
        for row in rows:
            pot = row.pot_product
            # Get primary image URL safely
            image_url = None
            try:
                urls = pot.get_card_image_urls(limit=1)
                image_url = urls[0] if urls else None
            except Exception:
                pass
 
            price = pot.base_price
            stock = pot.base_stock or 0
 
            data.append({
                'id': row.id,
                'pot_product_id': pot.id,
                'name': pot.name,
                'price': str(price) if price is not None else '0.00',
                'stock': stock,
                'in_stock': stock > 0,
                'image_url': image_url,
                'display_order': row.display_order,
            })
 
        return JsonResponse({'pot_addons': data})
 
 
class ProductPotCandidatesApiView(View):
    """
    GET /admin/products/<pk>/pot-candidates/?q=terra
    Search pot products that can be linked to this plant.
    Excludes pots already linked.
    """
 
    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        q = (request.GET.get('q') or '').strip()
 
        cat_ids = _pot_category_ids()
        if not cat_ids:
            return JsonResponse({
                'products': [],
                'warning': (
                    'No active category with slug "pot" or "pots" found. '
                    'Create a category named "Pots" first.'
                ),
            })
 
        already_linked = set(
            product.pot_addons.values_list('pot_product_id', flat=True)
        )
 
        qs = (
            Product.objects.filter(
                is_active=True,
                category_id__in=cat_ids,
            )
            .exclude(pk__in=already_linked)
            .exclude(pk=product.pk)
        )
 
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(slug__icontains=q)
            )
 
        qs = qs.order_by('name')[:40]
 
        return JsonResponse({
            'products': [
                {
                    'id': p.id,
                    'name': p.name,
                    'price': str(p.base_price) if p.base_price is not None else '0.00',
                    'stock': p.base_stock or 0,
                }
                for p in qs
            ]
        })
 
 
class ProductPotAddonAddApiView(View):
    """
    POST /admin/products/<pk>/pot-addons/add/
    Body: { "pot_product_id": 42 }
    Links a pot product to this plant product.
    """
 
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
 
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse(
                {'success': False, 'errors': {'__all__': ['Invalid JSON']}},
                status=400,
            )
 
        try:
            pot_id = int(data.get('pot_product_id'))
        except (TypeError, ValueError):
            return JsonResponse(
                {'success': False, 'errors': {'pot_product_id': ['Invalid product ID.']}},
                status=400,
            )
 
        # Validate it's actually a pot product
        cat_ids = _pot_category_ids()
        if not cat_ids:
            return JsonResponse(
                {
                    'success': False,
                    'errors': {
                        '__all__': [
                            'No active "pots" category found. '
                            'Create a category with slug "pot" or "pots" first.'
                        ]
                    },
                },
                status=400,
            )
 
        pot = Product.objects.filter(
            pk=pot_id,
            is_active=True,
            category_id__in=cat_ids,
        ).first()
 
        if not pot:
            return JsonResponse(
                {
                    'success': False,
                    'errors': {
                        'pot_product_id': [
                            'Choose an active product from the Pots category.'
                        ]
                    },
                },
                status=400,
            )
 
        if pot.pk == product.pk:
            return JsonResponse(
                {
                    'success': False,
                    'errors': {'pot_product_id': ['A product cannot be its own pot addon.']},
                },
                status=400,
            )
 
        # Compute next display_order
        next_order = (
            product.pot_addons.aggregate(m=Max('display_order')).get('m') or -1
        ) + 1
 
        try:
            row = ProductPotAddon.objects.create(
                plant_product=product,
                pot_product=pot,
                display_order=next_order,
            )
        except IntegrityError:
            return JsonResponse(
                {
                    'success': False,
                    'errors': {'__all__': ['This pot is already linked to this product.']},
                },
                status=400,
            )
 
        image_url = None
        try:
            urls = pot.get_card_image_urls(limit=1)
            image_url = urls[0] if urls else None
        except Exception:
            pass
 
        return JsonResponse({
            'success': True,
            'pot_addon': {
                'id': row.id,
                'pot_product_id': pot.id,
                'name': pot.name,
                'price': str(pot.base_price) if pot.base_price is not None else '0.00',
                'stock': pot.base_stock or 0,
                'in_stock': (pot.base_stock or 0) > 0,
                'image_url': image_url,
                'display_order': row.display_order,
            },
        })
 
 
class ProductPotAddonDeleteApiView(View):
    """
    POST /admin/products/<pk>/pot-addons/<row_id>/delete/
    Unlinks a pot addon from this plant product.
    """
 
    def post(self, request, pk, row_id):
        # Scope to product for safety
        product = get_object_or_404(Product, pk=pk)
        row = get_object_or_404(ProductPotAddon, pk=row_id, plant_product=product)
        row.delete()
        return JsonResponse({'success': True})
 
 
class ProductPotAddonReorderApiView(View):
    """
    POST /admin/products/<pk>/pot-addons/reorder/
    Body: { "order": [row_id1, row_id2, ...] }
    """
 
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
 
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse(
                {'success': False, 'errors': {'__all__': ['Invalid JSON']}},
                status=400,
            )
 
        order = data.get('order')
        if not isinstance(order, list):
            return JsonResponse(
                {'success': False, 'errors': {'order': ['Must be a list of IDs.']}},
                status=400,
            )
 
        valid_ids = set(
            product.pot_addons.values_list('id', flat=True)
        )
        for display_order, row_id in enumerate(order):
            if row_id in valid_ids:
                ProductPotAddon.objects.filter(
                    pk=row_id, plant_product=product
                ).update(display_order=display_order)
 
        return JsonResponse({'success': True})