"""
State-based delivery serviceability service.
Replaces the old pincode-based `app/services/pincode.py`.

Public API
----------
get_deliverable_states_for_product(product_id)  → QuerySet[DeliveryState]
is_state_deliverable_for_product(product_id, state_id) → bool
get_all_active_states()  → QuerySet[DeliveryState]
set_product_delivery_states(product_id, state_ids)  → None
serviceability_payload(*, product_id, state_id)  → dict
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.db import transaction
from django.db.models import QuerySet


# ── Read helpers ───────────────────────────────────────────────────────────────

def get_deliverable_states_for_product(product_id: int) -> QuerySet:
    """
    Return active DeliveryState objects this product ships to,
    ordered by display_order (south-first).
    Used to populate the customer dropdown on PDP.
    """
    from app.models import DeliveryState, ProductDeliveryState

    state_ids = (
        ProductDeliveryState.objects
        .filter(product_id=product_id)
        .values_list("state_id", flat=True)
    )
    return (
        DeliveryState.objects
        .filter(pk__in=state_ids, is_active=True)
        .order_by("display_order", "name")
    )


def is_state_deliverable_for_product(product_id: int, state_id: int) -> bool:
    """
    True if the product has a ProductDeliveryState row for this state.
    Used at checkout validation.
    """
    from app.models import ProductDeliveryState

    return (
        ProductDeliveryState.objects
        .filter(
            product_id=product_id,
            state_id=state_id,
            state__is_active=True,
        )
        .exists()
    )


def get_all_active_states() -> QuerySet:
    """
    All active states ordered for display.
    Used to populate seller-side checkbox list in product edit form.
    """
    from app.models import DeliveryState

    return DeliveryState.objects.filter(is_active=True).order_by("display_order", "name")


def get_states_by_region() -> Dict[str, List]:
    """
    Returns states grouped by region — useful for rendering grouped checkboxes
    in the seller admin UI.
    e.g. { "south": [<Kerala>, <Tamil Nadu>, ...], "west": [...], ... }
    """
    from app.models import DeliveryState

    region_order = ["south", "west", "central", "east", "north", "northeast", "ut"]
    states = list(DeliveryState.objects.filter(is_active=True).order_by("display_order", "name"))

    grouped: Dict[str, List] = {r: [] for r in region_order}
    for state in states:
        grouped.setdefault(state.region, []).append(state)
    # Drop empty regions
    return {k: v for k, v in grouped.items() if v}


# ── Write helpers ──────────────────────────────────────────────────────────────

def set_product_delivery_states(product_id: int, state_ids: List[int]) -> None:
    """
    Atomically replace the delivery-state list for a product.

    - Deletes all existing ProductDeliveryState rows for this product.
    - Bulk-creates new rows for the given state_ids.
    - Silently ignores invalid / inactive state_ids.

    Called by ProductDeliveryStateForm.save() and any API endpoint.
    """
    from app.models import DeliveryState, ProductDeliveryState

    # Filter to only valid, active states
    valid_ids = set(
        DeliveryState.objects
        .filter(pk__in=state_ids, is_active=True)
        .values_list("pk", flat=True)
    )

    with transaction.atomic():
        ProductDeliveryState.objects.filter(product_id=product_id).delete()
        if valid_ids:
            ProductDeliveryState.objects.bulk_create([
                ProductDeliveryState(product_id=product_id, state_id=sid)
                for sid in valid_ids
            ])


def add_product_delivery_state(product_id: int, state_id: int) -> bool:
    """
    Add a single state to a product's delivery list.
    Returns True if added, False if already existed.
    """
    from app.models import ProductDeliveryState, DeliveryState

    if not DeliveryState.objects.filter(pk=state_id, is_active=True).exists():
        return False

    _, created = ProductDeliveryState.objects.get_or_create(
        product_id=product_id,
        state_id=state_id,
    )
    return created


def remove_product_delivery_state(product_id: int, state_id: int) -> bool:
    """
    Remove a single state from a product's delivery list.
    Returns True if removed, False if it wasn't there.
    """
    from app.models import ProductDeliveryState

    deleted, _ = ProductDeliveryState.objects.filter(
        product_id=product_id,
        state_id=state_id,
    ).delete()
    return deleted > 0


# ── Serviceability payload (used by AJAX views + checkout) ────────────────────

def serviceability_payload(
    *,
    product_id: int,
    state_id: Optional[int],
) -> Dict[str, Any]:
    """
    Single unified response dict for both:
    - AJAX endpoint (PDP state dropdown interaction)
    - Checkout form validation

    Always includes the full deliverable_states list so the frontend
    can re-render the dropdown without a second request.
    """
    deliverable_qs = get_deliverable_states_for_product(product_id)
    deliverable_list = [
        {
            "id":     s.id,
            "name":   s.name,
            "code":   s.code,
            "region": s.region,
        }
        for s in deliverable_qs
    ]

    # No state selected yet — just return the list
    if not state_id:
        return {
            "serviceable":        False,
            "state_id":           None,
            "state_name":         None,
            "deliverable_states": deliverable_list,
            "message":            "Please select your delivery state.",
        }

    # Check if selected state is in the product's list
    selected = next((s for s in deliverable_qs if s.id == state_id), None)

    if selected:
        return {
            "serviceable":        True,
            "state_id":           selected.id,
            "state_name":         selected.name,
            "deliverable_states": deliverable_list,
            "message":            f"Delivery available to {selected.name} ✓",
        }

    # State exists globally but this product doesn't ship there
    from app.models import DeliveryState
    try:
        state_name = DeliveryState.objects.get(pk=state_id).name
    except DeliveryState.DoesNotExist:
        state_name = "selected state"

    return {
        "serviceable":        False,
        "state_id":           state_id,
        "state_name":         state_name,
        "deliverable_states": deliverable_list,
        "message":            f"Sorry, we don't currently deliver to {state_name}.",
    }


# ── Combo serviceability (checks all component products) ──────────────────────

def serviceability_payload_for_combo(
    *,
    combo_id: int,
    state_id: Optional[int],
) -> Dict[str, Any]:
    """
    For a Combo, check that ALL component products deliver to the state.
    Returns the intersection of deliverable states across all components.
    """
    from app.models import ComboItem  # adjust import to your combo model

    component_pids = list(
        ComboItem.objects
        .filter(combo_id=combo_id)
        .values_list("product_id", flat=True)
    )

    if not component_pids:
        return {
            "serviceable": False,
            "state_id": state_id,
            "state_name": None,
            "deliverable_states": [],
            "message": "Combo has no products.",
        }

    # Intersection: states deliverable by ALL components
    from app.models import DeliveryState, ProductDeliveryState

    # Start with states of first product, intersect with each subsequent product
    common_state_ids = set(
        ProductDeliveryState.objects
        .filter(product_id=component_pids[0])
        .values_list("state_id", flat=True)
    )
    for pid in component_pids[1:]:
        pid_state_ids = set(
            ProductDeliveryState.objects
            .filter(product_id=pid)
            .values_list("state_id", flat=True)
        )
        common_state_ids &= pid_state_ids

    deliverable_qs = (
        DeliveryState.objects
        .filter(pk__in=common_state_ids, is_active=True)
        .order_by("display_order", "name")
    )
    deliverable_list = [
        {"id": s.id, "name": s.name, "code": s.code, "region": s.region}
        for s in deliverable_qs
    ]

    if not state_id:
        return {
            "serviceable": False,
            "state_id": None,
            "state_name": None,
            "deliverable_states": deliverable_list,
            "message": "Please select your delivery state.",
        }

    selected = next((s for s in deliverable_qs if s.id == state_id), None)
    if selected:
        return {
            "serviceable": True,
            "state_id": selected.id,
            "state_name": selected.name,
            "deliverable_states": deliverable_list,
            "message": f"Delivery available to {selected.name} ✓",
        }

    from app.models import DeliveryState
    try:
        state_name = DeliveryState.objects.get(pk=state_id).name
    except DeliveryState.DoesNotExist:
        state_name = "selected state"

    return {
        "serviceable": False,
        "state_id": state_id,
        "state_name": state_name,
        "deliverable_states": deliverable_list,
        "message": f"Sorry, we don't currently deliver this combo to {state_name}.",
    }