"""Combo availability helpers (rental pricing moved to dedicated rental module)."""

from __future__ import annotations

from django.core.exceptions import ValidationError


def combo_component_qs(product):
    return product.combo_components.select_related('component_product').order_by('display_order', 'id')


def combo_is_in_stock(product, *, multiplier: int = 1) -> bool:
    """Combo available only if every simple child has enough base_stock."""
    from ..models import Product

    if not getattr(product, 'is_combo_product', False):
        return True
    mult = max(1, int(multiplier))
    rows = list(combo_component_qs(product))
    if not rows:
        return False
    for row in rows:
        child: Product = row.component_product
        need = int(row.quantity) * mult
        if child.has_variants():
            return False
        if (child.base_stock or 0) < need:
            return False
    return True


def assert_combo_children_allowed(product):
    if not getattr(product, 'is_combo_product', False):
        return
    rows = list(combo_component_qs(product))
    if not rows:
        raise ValidationError('Combo products must include at least one component.')
    seen = set()
    for row in rows:
        cid = row.component_product_id
        if cid == product.pk:
            raise ValidationError('A combo cannot include itself as a component.')
        if cid in seen:
            raise ValidationError('Duplicate component in combo.')
        seen.add(cid)
        if row.component_product.has_variants():
            raise ValidationError(f'Combo component "{row.component_product.name}" must be a simple product (no variants).')
        if getattr(row.component_product, 'is_combo_product', False):
            raise ValidationError('Nested combo products are not supported.')
