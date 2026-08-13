"""
State-based delivery serviceability and charge service.

Delivery charge is centralized on DeliveryState.delivery_charge — one fixed
charge per state, applied to every product. ProductDeliveryState only records
serviceability (which states a product ships to). Pack rounding is pooled
across the whole cart: ceil(total_cart_qty / DELIVERY_PACK_SIZE) packs,
billed once at the selected state's charge.

Public API
----------
resolve_delivery_state_id(...)  → int | None
get_deliverable_states_for_product(product_id)  → QuerySet[DeliveryState]
is_state_deliverable_for_product(product_id, state_id) → bool
get_all_active_states()  → QuerySet[DeliveryState]
set_product_delivery_states(product_id, state_ids)  → None
set_state_delivery_charges(charges)  → None
get_state_delivery_charge(state_id) → Decimal | None
get_product_delivery_charge(product_id, state_id) → Decimal | None
get_combo_delivery_charge(combo_id, state_id) → Decimal | None
compute_cart_delivery_charges(items, state_id) → CartDeliveryBreakdown
  total = state_charge × ceil(total_cart_qty / DELIVERY_PACK_SIZE)  # pooled across cart
delivery_pack_upsell_message(quantity) → str
serviceability_payload(*, product_id, state_id)  → dict
get_deliverable_states_payload(product_id) → list[dict]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet


ZERO = Decimal('0')


def _flat_fallback() -> Decimal:
    return Decimal(str(getattr(settings, 'FLAT_DELIVERY_CHARGE', 60)))


def _pack_size() -> int:
    """Pieces that share one state delivery charge, pooled across the whole cart."""
    try:
        size = int(getattr(settings, 'DELIVERY_PACK_SIZE', 2) or 1)
    except (TypeError, ValueError):
        size = 2
    return max(1, size)


def delivery_packs_for_quantity(quantity: int) -> int:
    """ceil(qty / DELIVERY_PACK_SIZE) — packs billed for this quantity."""
    qty = int(quantity or 0)
    if qty <= 0:
        return 0
    size = _pack_size()
    return (qty + size - 1) // size


def delivery_pack_free_slots(quantity) -> int:
    """Pieces that can still be added without starting a new delivery pack."""
    size = _pack_size()
    qty = int(quantity or 0)
    if qty <= 0 or size <= 1:
        return 0
    rem = qty % size
    return 0 if rem == 0 else size - rem


def delivery_pack_upsell_message(quantity, max_quantity=None) -> str:
    """Short checkout tip when another piece fits the current pack for free."""
    qty = int(quantity or 0)
    if max_quantity is not None:
        try:
            if qty >= int(max_quantity):
                return ''
        except (TypeError, ValueError):
            pass
    slots = delivery_pack_free_slots(qty)
    if slots == 1:
        return 'Add 1 more - no extra delivery'
    if slots > 1:
        return f'Add {slots} more - no extra delivery'
    return ''


def _as_decimal(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


# ── Read helpers ───────────────────────────────────────────────────────────────

def get_deliverable_state_ids_for_product(product_id: int) -> Optional[set]:
    """
    Return allowed state IDs for a product, or None when the product has no
    state restrictions (ships to all active states).
    """
    from app.models import ProductDeliveryState

    ids = set(
        ProductDeliveryState.objects
        .filter(product_id=product_id, state__is_active=True)
        .values_list('state_id', flat=True)
    )
    if not ids:
        return None
    return ids


def get_all_state_charges_map() -> Dict[int, Decimal]:
    """Map state_id → centralized delivery_charge (0 when unconfigured)."""
    from app.models import DeliveryState

    return {
        int(state_id): _as_decimal(charge)
        for state_id, charge in DeliveryState.objects.values_list('id', 'delivery_charge')
    }


def resolve_delivery_state_id(*, delivery_state=None, state_text: str = '') -> Optional[int]:
    """Resolve a DeliveryState PK from a model instance and/or legacy text state."""
    if delivery_state is not None:
        if hasattr(delivery_state, 'pk'):
            return delivery_state.pk
        try:
            return int(delivery_state)
        except (TypeError, ValueError):
            pass

    text = (state_text or '').strip()
    if not text:
        return None

    from app.models import DeliveryState

    ds = DeliveryState.objects.filter(is_active=True, name__iexact=text).first()
    if ds:
        return ds.pk
    match = DeliveryState.objects.filter(is_active=True, code__iexact=text).first()
    return match.pk if match else None


def get_deliverable_states_for_product(product_id: int) -> QuerySet:
    """
    Return active DeliveryState objects this product ships to.

    No configured ProductDeliveryState rows ⇒ unrestricted ⇒ all active states
    (same policy as is_state_deliverable_for_product / cart validation).
    """
    from app.models import DeliveryState

    allowed = get_deliverable_state_ids_for_product(product_id)
    if allowed is None:
        return get_all_active_states()
    return (
        DeliveryState.objects
        .filter(pk__in=allowed, is_active=True)
        .order_by('display_order', 'name')
    )


def is_state_deliverable_for_product(product_id: int, state_id: int) -> bool:
    """
    True if the product ships to this state.
    Products with no configured restrictions ship to all states.
    """
    allowed = get_deliverable_state_ids_for_product(product_id)
    if allowed is None:
        return True
    return state_id in allowed


def is_state_deliverable_for_combo(combo_id: int, state_id: int) -> bool:
    """True when every component product in the combo ships to this state."""
    from app.models import ComboItem

    component_pids = list(
        ComboItem.objects.filter(combo_id=combo_id).values_list('product_id', flat=True)
    )
    if not component_pids:
        return False
    return all(is_state_deliverable_for_product(pid, state_id) for pid in component_pids)


def get_all_active_states() -> QuerySet:
    """All active states ordered for display."""
    from app.models import DeliveryState

    return DeliveryState.objects.filter(is_active=True).order_by('display_order', 'name')


def get_states_by_region() -> Dict[str, List]:
    """Returns states grouped by region for seller admin UI."""
    from app.models import DeliveryState

    region_order = ['south', 'west', 'central', 'east', 'north', 'northeast', 'ut']
    states = list(DeliveryState.objects.filter(is_active=True).order_by('display_order', 'name'))

    grouped: Dict[str, List] = {r: [] for r in region_order}
    for state in states:
        grouped.setdefault(state.region, []).append(state)
    return {k: v for k, v in grouped.items() if v}


# ── Delivery charges ───────────────────────────────────────────────────────────

def get_state_delivery_charge(state_id: int) -> Optional[Decimal]:
    """
    Centralized per-pack delivery charge for a state (applies to every product).

    One pack covers up to DELIVERY_PACK_SIZE pieces (default 2).
    Returns None when the state has no configured charge yet (flat-rate fallback
    applies) — a configured value of 0 means explicitly free.
    """
    from app.models import DeliveryState

    charge = (
        DeliveryState.objects
        .filter(pk=state_id)
        .values_list('delivery_charge', flat=True)
        .first()
    )
    return _as_decimal(charge) if charge is not None else None


def get_product_delivery_charge(product_id: int, state_id: int) -> Optional[Decimal]:
    """
    Centralized per-pack delivery charge, if this product ships to this state.

    Returns None when the product doesn't ship to this state, or the state has
    no configured charge yet (caller falls back to flat rate).
    """
    if not is_state_deliverable_for_product(product_id, state_id):
        return None
    return get_state_delivery_charge(state_id)


def get_combo_delivery_charge(combo_id: int, state_id: int) -> Optional[Decimal]:
    """
    Centralized per-pack delivery charge, if every component product in the
    combo ships to this state (single state charge, not summed per component).
    """
    if not is_state_deliverable_for_combo(combo_id, state_id):
        return None
    return get_state_delivery_charge(state_id)


@dataclass
class CartDeliveryBreakdown:
    total: Decimal
    used_flat_fallback: bool = False
    state_missing: bool = False
    lines: Dict[int, Dict[str, Decimal]] = field(default_factory=dict)

    def line_for(self, item_id: int) -> Dict[str, Decimal]:
        return self.lines.get(item_id, {
            'delivery_charge_per_unit': ZERO,
            'total_delivery_charge': ZERO,
        })


def compute_cart_delivery_charges(items, state_id: Optional[int] = None) -> CartDeliveryBreakdown:
    """
    Cart-wide pooled delivery charge.

    Rules:
    - No state selected → ₹0 (checkout must prompt to select a state).
    - State selected → pool every line's quantity into one cart-wide total,
      bill ceil(total_qty / DELIVERY_PACK_SIZE) packs at the state's charge.
      Two products with qty 1 each share one pack, same as one product with
      qty 2. Callers are expected to have already blocked checkout for any
      undeliverable line (get_cart_delivery_issues), so every item here counts.
    - State has no configured charge → flat fallback once per order.

    Per-line charges are always zeroed in the returned breakdown — the pooled
    total isn't attributable to a single line, so it's carried at the order
    level (Order.shipping) instead, matching how the flat-fallback case has
    always been persisted.
    """
    if not state_id:
        return CartDeliveryBreakdown(total=ZERO, used_flat_fallback=False, state_missing=True)

    items = list(items)
    lines: Dict[int, Dict[str, Decimal]] = {
        item.id: {'delivery_charge_per_unit': ZERO, 'total_delivery_charge': ZERO}
        for item in items
        if getattr(item, 'id', None) is not None
    }

    total_qty = sum((int(getattr(item, 'quantity', 0) or 0) for item in items))
    packs = delivery_packs_for_quantity(total_qty)

    charge = get_state_delivery_charge(state_id)
    if charge is None:
        return CartDeliveryBreakdown(total=_flat_fallback(), used_flat_fallback=True, lines=lines)

    total = charge * Decimal(packs)
    return CartDeliveryBreakdown(total=total, used_flat_fallback=False, lines=lines)


# ── Write helpers ──────────────────────────────────────────────────────────────

def set_product_delivery_states(product_id: int, state_ids: List[int]) -> None:
    """Atomically replace the delivery-state list (serviceability) for a product."""
    from app.models import DeliveryState, ProductDeliveryState

    valid_ids = set(
        DeliveryState.objects
        .filter(pk__in=state_ids, is_active=True)
        .values_list('pk', flat=True)
    )

    with transaction.atomic():
        ProductDeliveryState.objects.filter(product_id=product_id).delete()
        if valid_ids:
            ProductDeliveryState.objects.bulk_create([
                ProductDeliveryState(product_id=product_id, state_id=sid)
                for sid in valid_ids
            ])


def set_state_delivery_charges(charges: Dict[int, Any]) -> None:
    """
    Bulk-update the centralized per-state delivery charge.

    charges: map of state_id → delivery_charge (Decimal/str/number/None).
    None clears the charge back to "unconfigured" (flat-rate fallback).
    """
    from app.models import DeliveryState

    with transaction.atomic():
        states = DeliveryState.objects.filter(pk__in=[int(k) for k in charges.keys()])
        to_update = []
        for state in states:
            value = charges.get(state.pk, charges.get(str(state.pk)))
            state.delivery_charge = None if value is None else _as_decimal(value)
            to_update.append(state)
        DeliveryState.objects.bulk_update(to_update, ['delivery_charge'])


def _state_list_with_charges(product_id: int, states) -> List[Dict[str, Any]]:
    charge_map = get_all_state_charges_map()
    return [
        {
            'id': s.id,
            'name': s.name,
            'code': s.code,
            'region': s.region,
            'delivery_charge': str(charge_map.get(s.id, ZERO)),
        }
        for s in states
    ]


def get_deliverable_states_payload(product_id: int) -> List[Dict[str, Any]]:
    """Deliverable states for a product, including per-state delivery charges."""
    return _state_list_with_charges(product_id, get_deliverable_states_for_product(product_id))


# ── Serviceability payload (used by AJAX views + checkout) ────────────────────

def serviceability_payload(
    *,
    product_id: int,
    state_id: Optional[int],
) -> Dict[str, Any]:
    """Unified response for PDP AJAX + checkout validation."""
    deliverable_qs = get_deliverable_states_for_product(product_id)
    deliverable_list = _state_list_with_charges(product_id, deliverable_qs)

    if not state_id:
        return {
            'serviceable': False,
            'state_id': None,
            'state_name': None,
            'delivery_charge': None,
            'deliverable_states': deliverable_list,
            'message': 'Please select your delivery state.',
        }

    selected = next((s for s in deliverable_qs if s.id == state_id), None)
    if selected:
        charge = get_product_delivery_charge(product_id, state_id)
        return {
            'serviceable': True,
            'state_id': selected.id,
            'state_name': selected.name,
            'delivery_charge': str(charge if charge is not None else ZERO),
            'deliverable_states': deliverable_list,
            'message': f'Delivery available to {selected.name} ✓',
        }

    from app.models import DeliveryState
    try:
        state_name = DeliveryState.objects.get(pk=state_id).name
    except DeliveryState.DoesNotExist:
        state_name = 'selected state'

    return {
        'serviceable': False,
        'state_id': state_id,
        'state_name': state_name,
        'delivery_charge': None,
        'deliverable_states': deliverable_list,
        'message': f"Sorry, we don't currently deliver to {state_name}.",
    }


def serviceability_payload_for_combo(
    *,
    combo_id: int,
    state_id: Optional[int],
) -> Dict[str, Any]:
    """For a Combo, ALL component products must deliver to the state."""
    from app.models import ComboItem, DeliveryState

    component_pids = list(
        ComboItem.objects
        .filter(combo_id=combo_id)
        .values_list('product_id', flat=True)
    )

    if not component_pids:
        return {
            'serviceable': False,
            'state_id': state_id,
            'state_name': None,
            'delivery_charge': None,
            'deliverable_states': [],
            'message': 'Combo has no products.',
        }

    common_state_ids = None
    for pid in component_pids:
        pid_state_ids = get_deliverable_state_ids_for_product(pid)
        if pid_state_ids is None:
            continue
        if common_state_ids is None:
            common_state_ids = set(pid_state_ids)
        else:
            common_state_ids &= pid_state_ids

    if common_state_ids is None:
        deliverable_qs = DeliveryState.objects.filter(is_active=True).order_by('display_order', 'name')
    elif not common_state_ids:
        deliverable_qs = DeliveryState.objects.none()
    else:
        deliverable_qs = (
            DeliveryState.objects
            .filter(pk__in=common_state_ids, is_active=True)
            .order_by('display_order', 'name')
        )

    charge_for_state = get_combo_delivery_charge(combo_id, state_id) if state_id else None
    deliverable_list = [
        {
            'id': s.id,
            'name': s.name,
            'code': s.code,
            'region': s.region,
            'delivery_charge': str(get_combo_delivery_charge(combo_id, s.id) or ZERO),
        }
        for s in deliverable_qs
    ]

    if not state_id:
        return {
            'serviceable': False,
            'state_id': None,
            'state_name': None,
            'delivery_charge': None,
            'deliverable_states': deliverable_list,
            'message': 'Please select your delivery state.',
        }

    selected = next((s for s in deliverable_qs if s.id == state_id), None)
    if selected:
        return {
            'serviceable': True,
            'state_id': selected.id,
            'state_name': selected.name,
            'delivery_charge': str(charge_for_state if charge_for_state is not None else ZERO),
            'deliverable_states': deliverable_list,
            'message': f'Delivery available to {selected.name} ✓',
        }

    try:
        state_name = DeliveryState.objects.get(pk=state_id).name
    except DeliveryState.DoesNotExist:
        state_name = 'selected state'

    return {
        'serviceable': False,
        'state_id': state_id,
        'state_name': state_name,
        'delivery_charge': None,
        'deliverable_states': deliverable_list,
        'message': f"Sorry, we don't currently deliver this combo to {state_name}.",
    }
