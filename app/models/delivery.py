"""
Delivery state models.

DeliveryState          — master list of all 28 Indian states + 8 UTs.
ProductDeliveryState   — bridge: which states a product ships to,
                         plus per-state delivery charge (per pack of up to
                         DELIVERY_PACK_SIZE pieces, default 2).
"""

from django.core.validators import MinValueValidator
from django.db import models
from .base import TimeStampedModel



class DeliveryState(models.Model):
    """
    All 28 states + 8 Union Territories of India.
    Seeded once via migration data; staff can toggle is_active.
    """

    REGION_CHOICES = [
        ("south",     "South India"),
        ("west",      "West India"),
        ("north",     "North India"),
        ("east",      "East India"),
        ("northeast", "North-East India"),
        ("central",   "Central India"),
        ("ut",        "Union Territory"),
    ]

    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(
        max_length=4,
        unique=True,
        help_text="ISO 3166-2:IN short code — e.g. KL, TN, MH",
    )
    region = models.CharField(
        max_length=20,
        choices=REGION_CHOICES,
        db_index=True,
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Lower = shown first in dropdowns. "
            "South states start at 0; UTs end at 60+."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Inactive states are hidden from both seller UI and customer UI.",
    )

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Delivery State"
        verbose_name_plural = "Delivery States"

    def __str__(self) -> str:
        return self.name

    def get_region_display_label(self) -> str:
        return dict(self.REGION_CHOICES).get(self.region, self.region)



class ProductDeliveryState(models.Model):
    """
    One row = this product can be delivered to this state at a given charge.

    delivery_charge is per pack (up to DELIVERY_PACK_SIZE pieces, default 2).
    Checkout bills ceil(qty / pack_size) packs per cart line.
    """

    product = models.ForeignKey(
        "app.Product",
        on_delete=models.CASCADE,
        related_name="delivery_states",
    )
    state = models.ForeignKey(
        DeliveryState,
        on_delete=models.CASCADE,
        related_name="product_deliveries",
    )
    delivery_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=(
            "Delivery charge for this product to this state "
            "(per pack of up to 2 pieces / ~1kg)."
        ),
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("product", "state")]
        ordering = ["state__display_order", "state__name"]
        verbose_name = "Product Delivery State"
        verbose_name_plural = "Product Delivery States"

    def __str__(self) -> str:
        return f"{self.product.name} → {self.state.name} (₹{self.delivery_charge})"