"""
DEPRECATED — Pincode-based delivery is replaced by state-based delivery.

This module is kept only so that any stale imports don't cause hard crashes
during the transition period. Remove it entirely once all references are gone.

See: app/services/state_delivery_service.py
"""

import warnings
from typing import Optional, Tuple


def normalize_pincode(pincode: Optional[str]) -> str:
    warnings.warn(
        "pincode.normalize_pincode() is deprecated. "
        "Delivery is now state-based. See state_delivery_service.py.",
        DeprecationWarning,
        stacklevel=2,
    )
    if not pincode:
        return ""
    return "".join(c for c in str(pincode).strip() if c.isdigit())


def is_pincode_serviceable(pincode: Optional[str]) -> bool:
    warnings.warn(
        "pincode.is_pincode_serviceable() is deprecated. "
        "Delivery is now state-based. Always returns False.",
        DeprecationWarning,
        stacklevel=2,
    )
    return False


def allowed_pincode_list() -> Tuple[str, ...]:
    warnings.warn(
        "pincode.allowed_pincode_list() is deprecated. Returns empty tuple.",
        DeprecationWarning,
        stacklevel=2,
    )
    return ()