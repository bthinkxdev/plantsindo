"""
Unified availability / serviceability service.
Now state-based instead of pincode-based.

Backward-compatible: old callers that pass `pincode=` still work
(pincode param is accepted but ignored).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.state_delivery_service import (
    serviceability_payload,
    serviceability_payload_for_combo,
)


def serviceability_for_product(
    *,
    product_id: int,
    state_id: Optional[int] = None,
    combo_id: Optional[int] = None,
    # ── Legacy kwargs — accepted but no longer used ────────────────────────
    pincode: Optional[str] = None,
    product_is_combo: bool = False,
    line_type: str = "purchase",
) -> Dict[str, Any]:
    """
    Returns a serviceability dict:
    {
        serviceable: bool,
        state_id: int | None,
        state_name: str | None,
        deliverable_states: [{"id", "name", "code", "region"}, ...],
        message: str,
    }

    For combos, pass combo_id instead of product_id —
    it checks the intersection of all component products' delivery states.
    """
    if product_is_combo and combo_id:
        return serviceability_payload_for_combo(combo_id=combo_id, state_id=state_id)

    return serviceability_payload(product_id=product_id, state_id=state_id)