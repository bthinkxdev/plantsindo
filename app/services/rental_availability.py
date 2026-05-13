from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Q


def _dates_valid(start: date, end: date) -> None:
    if not start or not end:
        raise ValidationError('Select rental start and end dates.')
    if end < start:
        raise ValidationError('Rental end date must be on or after start date.')


def _overlap_q(start: date, end: date) -> Q:
    # Overlap condition: existing.start <= end AND existing.end >= start
    return Q(rental_start_date__lte=end) & Q(rental_end_date__gte=start)


def _blocking_statuses():
    from app.models import RentalBooking

    return (RentalBooking.Status.PENDING, RentalBooking.Status.ACTIVE, RentalBooking.Status.COMPLETED)


def assert_product_available_for_rent(*, product, start: date, end: date, exclude_booking_id: int | None = None) -> None:
    """
    Raises ValidationError if the product is not available for rent
    for the given [start, end] date range.
    """
    from app.models import RentalBooking

    _dates_valid(start, end)

    qs = RentalBooking.objects.filter(product=product, status__in=_blocking_statuses()).filter(_overlap_q(start, end))
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)
    if qs.exists():
        raise ValidationError('This product is already booked for the selected dates.')


def assert_combo_available_for_rent(*, combo_product, start: date, end: date, exclude_booking_id: int | None = None) -> None:
    """
    Combo availability is determined by checking all component products for overlaps.
    """
    from app.services.rental_catalog import combo_component_qs

    _dates_valid(start, end)
    for row in combo_component_qs(combo_product):
        child = row.component_product
        assert_product_available_for_rent(product=child, start=start, end=end, exclude_booking_id=exclude_booking_id)


def assert_available_for_rent(*, product, start: date, end: date, exclude_booking_id: int | None = None) -> None:
    if getattr(product, 'is_combo_product', False):
        assert_combo_available_for_rent(combo_product=product, start=start, end=end, exclude_booking_id=exclude_booking_id)
    else:
        assert_product_available_for_rent(product=product, start=start, end=end, exclude_booking_id=exclude_booking_id)

