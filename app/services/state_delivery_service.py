"""
State-based delivery serviceability and charge service.

Public API
----------
resolve_delivery_state_id(...)  → int | None
get_deliverable_states_for_product(product_id)  → QuerySet[DeliveryState]
is_state_deliverable_for_product(product_id, state_id) → bool
get_all_active_states()  → QuerySet[DeliveryState]
set_product_delivery_states(product_id, state_ids, charges=None)  → None
get_product_delivery_charge(product_id, state_id) → Decimal | None
get_combo_delivery_charge(combo_id, state_id) → Decimal | None
resolve_item_delivery_charge(item, state_id) → (per_pack, line_total, has_row)
compute_cart_delivery_charges(items, state_id) → CartDeliveryBreakdown
  line_total = state_charge × ceil(qty / DELIVERY_PACK_SIZE)  # Approach A, per line
delivery_pack_upsell_message(quantity) → str
serviceability_payload(*, product_id, state_id)  → dict
get_deliverable_states_payload(product_id) → list[dict]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet


ZERO = Decimal('0')


def _flat_fallback() -> Decimal:
    return Decimal(str(getattr(settings, 'FLAT_DELIVERY_CHARGE', 60)))


def _pack_size() -> int:
    """Pieces that share one state delivery charge (Approach A: per cart line)."""
    try:
        size = int(getattr(settings, 'DELIVERY_PACK_SIZE', 2) or 1)
    except (TypeError, ValueError):
        size = 2
    return max(1, size)


def delivery_packs_for_quantity(quantity: int) -> int:
    """ceil(qty / DELIVERY_PACK_SIZE) — packs billed for a single cart line."""
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


def get_product_state_charges_map(product_id: int) -> Dict[int, Decimal]:
    """Map state_id → delivery_charge for a product."""
    from app.models import ProductDeliveryState

    return {
        int(state_id): _as_decimal(charge)
        for state_id, charge in ProductDeliveryState.objects
        .filter(product_id=product_id)
        .values_list('state_id', 'delivery_charge')
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

def get_product_delivery_charge(product_id: int, state_id: int) -> Optional[Decimal]:
    """
    Per-pack delivery charge for product × state.

    One pack covers up to DELIVERY_PACK_SIZE pieces (default 2).
    Returns Decimal when a ProductDeliveryState row exists.
    Returns None when the product has no row for this state
    (unrestricted, or not deliverable — caller must check serviceability).
    """
    from app.models import ProductDeliveryState

    row = (
        ProductDeliveryState.objects
        .filter(product_id=product_id, state_id=state_id)
        .only('delivery_charge')
        .first()
    )
    if row is None:
        return None
    return _as_decimal(row.delivery_charge)


def get_combo_delivery_charge(combo_id: int, state_id: int) -> Optional[Decimal]:
    """
    Per-pack combo delivery charge = sum of component product charges for the state.

    Returns None only when no component has a configured charge row for the state.
    Component quantities in the combo multiply that component's per-pack charge
    when building one combo unit's ship fee; cart-line pack math still applies
    to combo quantity via resolve_item_delivery_charge.
    """
    from app.models import ComboItem

    components = list(
        ComboItem.objects.filter(combo_id=combo_id).values_list('product_id', 'quantity')
    )
    if not components:
        return None

    total = ZERO
    any_row = False
    for product_id, qty in components:
        charge = get_product_delivery_charge(product_id, state_id)
        if charge is None:
            continue
        any_row = True
        total += charge * Decimal(int(qty or 1))
    return total if any_row else None


def resolve_item_delivery_charge(item, state_id: Optional[int]) -> Tuple[Decimal, Decimal, bool]:
    """
    Resolve (per_pack, line_total, has_configured_row) for a cart/order line.

    line_total = per_pack × ceil(quantity / DELIVERY_PACK_SIZE).

    has_configured_row is True when the product/combo has a ProductDeliveryState
    row for the selected state (charge may still be zero).
    """
    if not state_id:
        return ZERO, ZERO, False

    per_pack: Optional[Decimal]
    if getattr(item, 'combo_id', None):
        per_pack = get_combo_delivery_charge(item.combo_id, state_id)
    elif getattr(item, 'product_id', None):
        per_pack = get_product_delivery_charge(item.product_id, state_id)
    else:
        per_pack = None

    if per_pack is None:
        return ZERO, ZERO, False

    packs = Decimal(delivery_packs_for_quantity(getattr(item, 'quantity', 1)))
    return per_pack, per_pack * packs, True


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
    Sum per-line state delivery charges for a cart.

    Rules:
    - No state selected → ₹0 (checkout must prompt to select a state).
    - State selected + at least one line has a configured charge row →
      sum(state_charge × ceil(qty / DELIVERY_PACK_SIZE)) across lines
      (missing rows contribute 0). Pack size is per line (Approach A).
    - State selected + no lines have a charge row → flat fallback once per order
      (preserves behaviour for unrestricted catalogues).
    """
    if not state_id:
        return CartDeliveryBreakdown(total=ZERO, used_flat_fallback=False, state_missing=True)

    flat = _flat_fallback()
    lines: Dict[int, Dict[str, Decimal]] = {}
    total = ZERO
    any_configured = False

    for item in items:
        per_unit, line_total, has_row = resolve_item_delivery_charge(item, state_id)
        item_id = getattr(item, 'id', None)
        if item_id is not None:
            lines[item_id] = {
                'delivery_charge_per_unit': per_unit,
                'total_delivery_charge': line_total,
            }
        if has_row:
            any_configured = True
            total += line_total

    if not any_configured:
        return CartDeliveryBreakdown(total=flat, used_flat_fallback=True, lines=lines)

    return CartDeliveryBreakdown(total=total, used_flat_fallback=False, lines=lines)


# ── Write helpers ──────────────────────────────────────────────────────────────

def set_product_delivery_states(
    product_id: int,
    state_ids: List[int],
    charges: Optional[Dict[int, Any]] = None,
) -> None:
    """
    Atomically replace the delivery-state list for a product.

    charges: optional map of state_id → delivery_charge (Decimal/str/number).
    Every selected state should have a non-negative charge; missing keys default to 0.
    """
    from app.models import DeliveryState, ProductDeliveryState

    valid_ids = set(
        DeliveryState.objects
        .filter(pk__in=state_ids, is_active=True)
        .values_list('pk', flat=True)
    )
    charge_map = charges or {}

    with transaction.atomic():
        ProductDeliveryState.objects.filter(product_id=product_id).delete()
        if valid_ids:
            ProductDeliveryState.objects.bulk_create([
                ProductDeliveryState(
                    product_id=product_id,
                    state_id=sid,
                    delivery_charge=_as_decimal(charge_map.get(sid, charge_map.get(str(sid), 0))),
                )
                for sid in valid_ids
            ])


def _state_list_with_charges(product_id: int, states) -> List[Dict[str, Any]]:
    charge_map = get_product_state_charges_map(product_id)
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
