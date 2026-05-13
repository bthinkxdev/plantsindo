"""Combo (bundle) availability: components are simple Products with base_stock."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from app.models import Combo, ComboItem, Product


def combo_items_qs(combo: Combo):
    return combo.items.select_related('product').order_by('display_order', 'id')


def prefetch_combo_items():
    return Prefetch('items', queryset=ComboItem.objects.select_related('product').order_by('display_order', 'id'))


def combo_is_in_stock(combo: Combo, *, multiplier: int = 1) -> bool:
    if not getattr(combo, 'pk', None):
        return False
    mult = max(1, int(multiplier))
    rows = list(combo_items_qs(combo))
    if not rows:
        return False
    for row in rows:
        child: Product = row.product
        need = int(row.quantity) * mult
        if child.has_variants():
            return False
        if getattr(child, 'is_combo_product', False):
            return False
        if (child.base_stock or 0) < need:
            return False
    return True


def assert_combo_valid(combo: Combo) -> None:
    """Validate structure for a persisted combo (at least one line, no nested bundles, simple children)."""
    if not getattr(combo, 'pk', None):
        return
    rows = list(combo_items_qs(combo))
    if not rows:
        raise ValidationError('Combo must include at least one product.')
    seen = set()
    for row in rows:
        pid = row.product_id
        if pid in seen:
            raise ValidationError('Duplicate product in combo.')
        seen.add(pid)
        p = row.product
        if p.has_variants():
            raise ValidationError(f'Combo component "{p.name}" must be a simple product (no variants).')
        if getattr(p, 'is_combo_product', False):
            raise ValidationError('Nested combo products are not supported as components.')
