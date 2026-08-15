import threading
from dataclasses import dataclass
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils.crypto import get_random_string
from ..models import Address, Cart, CartItem, Combo, Order, OrderItem, Payment, Product, Variant, Wishlist


def decrement_stock_for_order_item(order_item: OrderItem) -> None:
    """Reduce inventory for a confirmed order line (COD or after online payment)."""
    from ..models import ProductPotAddon

    if order_item.combo_id and order_item.combo:
        for row in order_item.combo.items.all():
            dec = order_item.quantity * int(row.quantity or 1)
            Product.objects.filter(pk=row.product_id).update(base_stock=F('base_stock') - dec)
        return

    product = order_item.product
    if not product:
        return

    if getattr(product, 'is_combo_product', False):
        for row in product.combo_components.select_related('component_product'):
            dec = order_item.quantity * row.quantity
            Product.objects.filter(pk=row.component_product_id).update(base_stock=F('base_stock') - dec)
    elif order_item.selected_variant_id:
        Variant.objects.filter(pk=order_item.selected_variant_id).update(
            stock_quantity=F('stock_quantity') - order_item.quantity
        )
    else:
        Product.objects.filter(pk=product.pk).update(base_stock=F('base_stock') - order_item.quantity)

    if order_item.selected_pot_name and order_item.pot_unit_price and order_item.product_id:
        pot_product_id = (
            ProductPotAddon.objects.filter(
                plant_product_id=order_item.product_id,
                pot_product__name=order_item.selected_pot_name,
            )
            .values_list('pot_product_id', flat=True)
            .first()
        )
        if pot_product_id:
            Product.objects.filter(pk=pot_product_id).update(
                base_stock=F('base_stock') - order_item.quantity
            )

def send_order_notification_email_async(order, request=None):
    thread = threading.Thread(target=send_order_notification_email, args=(order, request), daemon=True)
    thread.start()
    return thread

def send_order_notification_email(order, request=None):
    try:
        admin_emails = getattr(settings, 'ADMIN_NOTIFICATION_EMAILS', [])
        if not admin_emails:
            return False
        try:
            if request:
                order_url = request.build_absolute_uri(f'/dashboard/orders/{order.order_number}/')
            else:
                site_domain = getattr(settings, 'SITE_DOMAIN', 'https://queenorange.shop/')
                order_url = f'{site_domain}/dashboard/orders/{order.order_number}/'
        except Exception:
            order_url = f'Order #{order.order_number}'
        payment_method = 'Cash on Delivery'
        try:
            if hasattr(order, 'payment') and order.payment:
                payment_method = order.payment.get_method_display()
        except Exception:
            pass
        context = {'order': order, 'order_url': order_url, 'payment_method': payment_method, 'site_name': getattr(settings, 'SITE_BRAND', 'Plantsindo')}
        try:
            html_message = render_to_string('admin/order_notification_email.html', context)
            plain_message = render_to_string('admin/order_notification_email.txt', context)
        except Exception:
            return False
        try:
            send_mail(subject=f'New Order #{order.order_number} - ₹{order.total}', message=plain_message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=admin_emails, html_message=html_message, fail_silently=False)
            return True
        except Exception:
            return False
    except Exception:
        return False

def send_order_confirmation_email(order):
    try:
        from ..models import Order
        customer_email = ''
        try:
            if getattr(order, 'address', None) and getattr(order.address, 'email', ''):
                customer_email = (order.address.email or '').strip()
        except Exception:
            customer_email = ''
        if not customer_email and getattr(order, 'user', None):
            customer_email = (getattr(order.user, 'email', '') or '').strip()
        if not customer_email:
            return False
        status = getattr(order, 'status', None)
        if status == Order.Status.CONFIRMED:
            status_key = 'confirmed'
            subject = f'Your order #{order.order_number} is confirmed'
        elif status == Order.Status.SHIPPED:
            status_key = 'shipped'
            subject = f'Good news! Order #{order.order_number} is on the way'
        elif status == Order.Status.DELIVERED:
            status_key = 'delivered'
            subject = f'Order #{order.order_number} has been delivered'
        elif status == Order.Status.CANCELLED:
            status_key = 'cancelled'
            subject = f'Order #{order.order_number} has been cancelled'
        else:
            status_key = 'placed'
            subject = f'Thank you for your order #{order.order_number}'
        context = {'order': order, 'site_name': getattr(settings, 'SITE_BRAND', 'Plantsindo'), 'status_key': status_key}
        try:
            html_message = render_to_string('emails/order_confirmation.html', context)
            plain_message = render_to_string('emails/order_confirmation.txt', context)
        except Exception:
            if status_key == 'cancelled':
                plain_message = f'Your order #{order.order_number} has been cancelled. If you did not request this, please contact support.'
            elif status_key == 'shipped':
                plain_message = f"Your order #{order.order_number} has been shipped. You'll receive another update when it is delivered."
            elif status_key == 'delivered':
                plain_message = f'Your order #{order.order_number} has been delivered. We hope you enjoy your purchase!'
            elif status_key == 'confirmed':
                plain_message = f"Your order #{order.order_number} is confirmed. We'll let you know once it ships."
            else:
                plain_message = f'Thank you for your order #{order.order_number}. We will notify you as it is confirmed and shipped.'
            html_message = None
        send_mail(subject=subject, message=plain_message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[customer_email], html_message=html_message, fail_silently=True)
        return True
    except Exception:
        return False

def send_order_confirmation_email_async(order):
    try:
        thread = threading.Thread(target=send_order_confirmation_email, args=(order,), daemon=True)
        thread.start()
        return thread
    except Exception:
        return None

class CartError(Exception):
    pass

class StockError(CartError):
    pass


@dataclass
class CartStockIssue:
    item_id: int
    name: str
    issue: str
    message: str
    available_qty: int = 0
    requested_qty: int = 0


def inspect_cart_item_stock(item: CartItem) -> CartStockIssue | None:
    """Return a stock issue for a cart line, or None if the line is purchasable as-is."""
    from ..services.rental_catalog import combo_is_in_stock
    from ..services.combo_catalog import combo_is_in_stock as combo_bundle_in_stock

    if item.combo_id:
        c = item.combo
        name = c.name if c else 'Bundle'
        if not c or not c.is_active or not c.purchase_enabled:
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='unavailable',
                message=f'{name} is no longer available.',
                requested_qty=item.quantity,
            )
        if not combo_bundle_in_stock(c, multiplier=item.quantity):
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='out_of_stock',
                message=f'{name} is out of stock. Please remove it from your cart.',
                requested_qty=item.quantity,
            )
        return None

    product = item.product
    name = product.name if product else 'Product'
    if not product or not getattr(product, 'is_active', True):
        return CartStockIssue(
            item_id=item.id,
            name=name,
            issue='unavailable',
            message=f'{name} is no longer available.',
            requested_qty=item.quantity,
        )

    v = item.selected_variant
    if getattr(product, 'is_combo_product', False):
        if not combo_is_in_stock(product, multiplier=item.quantity):
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='out_of_stock',
                message=f'{name} is out of stock. Please remove it from your cart.',
                requested_qty=item.quantity,
            )
    elif v:
        avail = int(v.stock_quantity or 0)
        if not getattr(v, 'is_active', True) or avail <= 0:
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='out_of_stock',
                message=f'{name} is out of stock. Please remove it from your cart.',
                available_qty=0,
                requested_qty=item.quantity,
            )
        if item.quantity > avail:
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='insufficient',
                message=f'Only {avail} left for {name}. Reduce quantity or remove the item.',
                available_qty=avail,
                requested_qty=item.quantity,
            )
    else:
        if product.has_variants():
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='unavailable',
                message=f'{name} needs a variant selection. Please remove it and add again.',
                requested_qty=item.quantity,
            )
        avail = int(product.base_stock or 0)
        if avail <= 0:
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='out_of_stock',
                message=f'{name} is out of stock. Please remove it from your cart.',
                available_qty=0,
                requested_qty=item.quantity,
            )
        if item.quantity > avail:
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='insufficient',
                message=f'Only {avail} left for {name}. Reduce quantity or remove the item.',
                available_qty=avail,
                requested_qty=item.quantity,
            )

    if item.line_type == CartItem.LineKind.PURCHASE and item.selected_pot_id and item.selected_pot:
        pot = item.selected_pot
        pot_stock = int(pot.base_stock or 0)
        pot_name = pot.name
        if pot_stock <= 0:
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='pot_out_of_stock',
                message=f'Pot "{pot_name}" for {name} is out of stock. Remove the pot or remove the item.',
                requested_qty=item.quantity,
            )
        if item.quantity > pot_stock:
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='pot_insufficient',
                message=f'Only {pot_stock} pots left for "{pot_name}". Reduce quantity or change pot.',
                available_qty=pot_stock,
                requested_qty=item.quantity,
            )

    if item.line_type == CartItem.LineKind.RENTAL and item.rental_start_date and item.rental_end_date:
        from django.core.exceptions import ValidationError as DjangoValidationError
        from ..services.rental_availability import assert_available_for_rent
        try:
            assert_available_for_rent(product=product, start=item.rental_start_date, end=item.rental_end_date)
        except DjangoValidationError as exc:
            msg = '; '.join(getattr(exc, 'messages', []) or [str(exc)]) or 'Rental dates are no longer available.'
            return CartStockIssue(
                item_id=item.id,
                name=name,
                issue='unavailable',
                message=f'{name}: {msg}',
                requested_qty=item.quantity,
            )

    return None


def get_cart_stock_issues(items) -> list[CartStockIssue]:
    issues = []
    for item in items:
        issue = inspect_cart_item_stock(item)
        if issue:
            issues.append(issue)
    return issues


def format_cart_stock_error(issues: list[CartStockIssue]) -> str:
    if not issues:
        return ''
    if len(issues) == 1:
        return issues[0].message
    names = ', '.join(i.name for i in issues[:3])
    suffix = f' and {len(issues) - 3} more' if len(issues) > 3 else ''
    return (
        f'{len(issues)} items in your cart need attention ({names}{suffix}). '
        'Please remove or update unavailable items before checkout.'
    )


@dataclass
class CartDeliveryIssue:
    item_id: int
    name: str
    message: str
    state_name: str = ''


def get_cart_delivery_issues(items, state_id: int | None) -> list[CartDeliveryIssue]:
    """Return cart lines that cannot ship to the given DeliveryState."""
    if not state_id:
        return []

    from app.services.state_delivery_service import (
        is_state_deliverable_for_combo,
        is_state_deliverable_for_product,
        resolve_delivery_state_id,
    )
    from app.models import DeliveryState

    state_id = resolve_delivery_state_id(delivery_state=state_id)
    if not state_id:
        return []

    try:
        state_name = DeliveryState.objects.get(pk=state_id, is_active=True).name
    except DeliveryState.DoesNotExist:
        return []

    issues: list[CartDeliveryIssue] = []
    for item in items:
        if item.combo_id:
            name = item.combo.name if item.combo else 'Bundle'
            if not is_state_deliverable_for_combo(item.combo_id, state_id):
                issues.append(CartDeliveryIssue(
                    item_id=item.id,
                    name=name,
                    state_name=state_name,
                    message=f'Not deliverable in {state_name}',
                ))
            continue

        product = item.product
        if not product:
            continue
        if not is_state_deliverable_for_product(product.pk, state_id):
            issues.append(CartDeliveryIssue(
                item_id=item.id,
                name=product.name,
                state_name=state_name,
                message=f'Not deliverable in {state_name}',
            ))
    return issues


def format_cart_delivery_error(issues: list[CartDeliveryIssue]) -> str:
    """Short checkout/API status for undeliverable selections."""
    if not issues:
        return ''
    state_name = issues[0].state_name or 'this state'
    return f'Not deliverable in {state_name}'


@dataclass
class CartTotals:
    subtotal: object
    gst_total: object
    shipping: object
    total: object
    delivery_breakdown: object = None
    used_flat_fallback: bool = False
    state_missing: bool = False
    discount_amount: object = None
    coupon_code: str = ''


@dataclass
class CheckoutTotalsResult:
    """
    Single checkout presentation of cart totals + delivery status.
    Used by checkout SSR and /api/checkout/totals/.
    """
    subtotal: object
    gst_total: object
    shipping: object
    total: object
    status: str
    shipping_label: str
    delivery_issues: list
    delivery_message: str
    state_id: object = None
    delivery_breakdown: object = None
    used_flat_fallback: bool = False
    discount_amount: object = None
    coupon_code: str = ''
    coupon_message: str = ''
    coupon_error: str = ''

    @property
    def state_missing(self) -> bool:
        return self.status == 'state_required'

    @property
    def serviceable(self) -> bool:
        return self.status == 'ok'

    @property
    def checkout_blocked(self) -> bool:
        return self.status != 'ok'

    def as_cart_totals(self) -> CartTotals:
        from decimal import Decimal
        return CartTotals(
            subtotal=self.subtotal,
            gst_total=self.gst_total,
            shipping=self.shipping,
            total=self.total,
            delivery_breakdown=self.delivery_breakdown,
            used_flat_fallback=self.used_flat_fallback,
            state_missing=self.state_missing,
            discount_amount=self.discount_amount if self.discount_amount is not None else Decimal('0'),
            coupon_code=self.coupon_code or '',
        )

    def line_payload(self, items) -> list[dict]:
        breakdown = self.delivery_breakdown if self.serviceable else None
        blocked_ids = {issue.item_id for issue in self.delivery_issues}
        lines = []
        for item in items:
            line = breakdown.line_for(item.id) if breakdown else None
            lines.append({
                'item_id': item.id,
                'delivery_charge_per_unit': str(line['delivery_charge_per_unit']) if line else '0',
                'total_delivery_charge': str(line['total_delivery_charge']) if line else '0',
                'deliverable': item.id not in blocked_ids,
            })
        return lines

    def to_api_dict(self, items) -> dict:
        from decimal import Decimal

        from .state_delivery_service import delivery_pack_upsell_message

        discount = self.discount_amount if self.discount_amount is not None else Decimal('0')
        total_qty = sum((item.quantity for item in items))
        return {
            'success': True,
            'state_id': self.state_id,
            'state_selected': bool(self.state_id),
            'state_missing': self.state_missing,
            'serviceable': self.serviceable,
            'status': self.status,
            'delivery_issues': [
                {
                    'item_id': i.item_id,
                    'name': i.name,
                    'message': i.message,
                    'state_name': i.state_name,
                }
                for i in self.delivery_issues
            ],
            'delivery_message': self.delivery_message,
            'shipping_label': self.shipping_label,
            'subtotal': str(self.subtotal),
            'gst_total': str(self.gst_total or 0),
            'shipping': str(self.shipping),
            'discount_amount': str(discount),
            'coupon_code': self.coupon_code or '',
            'coupon_message': self.coupon_message or '',
            'coupon_error': self.coupon_error or '',
            'total': str(self.total),
            'checkout_blocked': self.checkout_blocked,
            'used_flat_fallback': self.used_flat_fallback if self.serviceable else False,
            'pack_upsell_message': delivery_pack_upsell_message(total_qty),
            'lines': self.line_payload(items),
        }


def shipping_label_for_amount(shipping) -> str:
    from decimal import Decimal
    amount = shipping if isinstance(shipping, Decimal) else Decimal(str(shipping or 0))
    if amount == 0:
        return 'Free'
    # Trim trailing .00 for display consistency with checkout UI.
    quantized = amount.quantize(Decimal('1')) if amount == amount.to_integral_value() else amount
    return f'₹{quantized}'


def _apply_coupon_to_checkout_result(
    result: CheckoutTotalsResult,
    *,
    coupon_code=None,
    user=None,
    email=None,
    phone=None,
) -> CheckoutTotalsResult:
    """Attach coupon discount to an existing CheckoutTotalsResult (mutates totals)."""
    from decimal import Decimal

    from .coupon_service import CouponError, validate_for_checkout

    code = (coupon_code or '').strip()
    if not code:
        result.discount_amount = Decimal('0')
        result.coupon_code = ''
        result.coupon_message = ''
        result.coupon_error = ''
        return result

    try:
        validated = validate_for_checkout(
            code,
            subtotal=result.subtotal,
            user=user,
            email=email or '',
            phone=phone or '',
        )
    except CouponError as exc:
        result.discount_amount = Decimal('0')
        result.coupon_code = ''
        result.coupon_message = ''
        result.coupon_error = exc.message
        return result

    discount = validated.discount_amount
    result.discount_amount = discount
    result.coupon_code = validated.code
    result.coupon_message = validated.message
    result.coupon_error = ''
    result.total = (result.subtotal or 0) + (result.gst_total or 0) + (result.shipping or 0) - discount
    return result


def resolve_checkout_totals(
    cart,
    state_id=None,
    items=None,
    coupon_code=None,
    user=None,
    email=None,
    phone=None,
) -> CheckoutTotalsResult:
    """
    Canonical checkout totals + delivery status.

    Rules:
    - No state → shipping excluded, status state_required
    - State with undeliverable lines → shipping excluded, status unavailable
    - Valid state → state charges (or flat fallback) included, status ok
    - Optional coupon_code → discount off subtotal (never shipping); GST unchanged
    """
    from decimal import Decimal

    if items is None:
        items = list(
            cart.items.select_related('product', 'combo', 'selected_variant', 'selected_pot')
            .prefetch_related('combo__items__product')
        )

    delivery_issues = get_cart_delivery_issues(items, state_id) if state_id else []
    delivery_message = format_cart_delivery_error(delivery_issues)

    if not state_id:
        base = CartService.compute_totals(cart, state_id=None)
        subtotal = base.subtotal or 0
        gst_total = base.gst_total or 0
        result = CheckoutTotalsResult(
            subtotal=subtotal,
            gst_total=gst_total,
            shipping=Decimal('0'),
            total=subtotal + gst_total,
            status='state_required',
            shipping_label='Please select the state',
            delivery_issues=[],
            delivery_message='',
            state_id=None,
            delivery_breakdown=getattr(base, 'delivery_breakdown', None),
            used_flat_fallback=False,
            discount_amount=Decimal('0'),
        )
        return _apply_coupon_to_checkout_result(
            result, coupon_code=coupon_code, user=user, email=email, phone=phone
        )

    if delivery_issues:
        base = CartService.compute_totals(cart, state_id=None)
        subtotal = base.subtotal or 0
        gst_total = base.gst_total or 0
        result = CheckoutTotalsResult(
            subtotal=subtotal,
            gst_total=gst_total,
            shipping=Decimal('0'),
            total=subtotal + gst_total,
            status='unavailable',
            shipping_label=delivery_message or 'Not deliverable in this state',
            delivery_issues=delivery_issues,
            delivery_message=delivery_message,
            state_id=state_id,
            delivery_breakdown=getattr(base, 'delivery_breakdown', None),
            used_flat_fallback=False,
            discount_amount=Decimal('0'),
        )
        return _apply_coupon_to_checkout_result(
            result, coupon_code=coupon_code, user=user, email=email, phone=phone
        )

    totals = CartService.compute_totals(cart, state_id=state_id)
    result = CheckoutTotalsResult(
        subtotal=totals.subtotal,
        gst_total=totals.gst_total,
        shipping=totals.shipping,
        total=totals.total,
        status='ok',
        shipping_label=shipping_label_for_amount(totals.shipping),
        delivery_issues=[],
        delivery_message='',
        state_id=state_id,
        delivery_breakdown=getattr(totals, 'delivery_breakdown', None),
        used_flat_fallback=bool(getattr(totals, 'used_flat_fallback', False)),
        discount_amount=Decimal('0'),
    )
    return _apply_coupon_to_checkout_result(
        result, coupon_code=coupon_code, user=user, email=email, phone=phone
    )


class CartService:

    @staticmethod
    def _ensure_session_key(request):
        if not request.session.session_key:
            request.session.save()
        return request.session.session_key

    @classmethod
    def get_or_create_cart(cls, request):
        user = getattr(request, 'user', None)
        user = user if user and user.is_authenticated else None
        if user:
            cart, _ = Cart.objects.get_or_create(user=user, status=Cart.Status.ACTIVE)
            return cart
        session_key = cls._ensure_session_key(request)
        cart = Cart.objects.filter(session_key=session_key, status=Cart.Status.ACTIVE, user__isnull=True).first()
        if not cart:
            cart = Cart.objects.create(session_key=session_key, status=Cart.Status.ACTIVE)
        return cart

    @classmethod
    def get_or_create_buy_now_cart(cls, request):
        user = getattr(request, 'user', None)
        user = user if user and user.is_authenticated else None
        if user:
            cart, _ = Cart.objects.get_or_create(user=user, status=Cart.Status.BUY_NOW)
            return cart
        session_key = cls._ensure_session_key(request)
        cart = Cart.objects.filter(session_key=session_key, status=Cart.Status.BUY_NOW, user__isnull=True).first()
        if not cart:
            cart = Cart.objects.create(session_key=session_key, status=Cart.Status.BUY_NOW)
        return cart

    @classmethod
    def get_checkout_cart(cls, request):
        mode = request.session.get('checkout_mode', 'cart')
        if mode == 'buy_now':
            return cls.get_or_create_buy_now_cart(request)
        return cls.get_or_create_cart(request)

    @classmethod
    def merge_carts(cls, user, session_key):
        if not user or not session_key:
            return
        try:
            session_cart = Cart.objects.get(session_key=session_key, status=Cart.Status.ACTIVE)
        except Cart.DoesNotExist:
            return
        user_cart, _ = Cart.objects.get_or_create(user=user, status=Cart.Status.ACTIVE)
        for item in session_cart.items.select_related('product', 'selected_variant', 'combo').all():
            rb = item.rental_billing_period or None
            ru = item.rental_period_count if item.line_type == CartItem.LineKind.RENTAL else None
            gift = bool(item.is_gift)
            rs = item.rental_start_date
            re = item.rental_end_date
            if item.combo_id:
                cls.add_combo_item(user_cart, item.combo, item.quantity, line_type=item.line_type, is_gift=gift)
            elif item.selected_variant_id:
                cls.add_item(user_cart, item.selected_variant, item.quantity, line_type=item.line_type, rental_billing=rb, rental_units=ru, rental_start_date=rs, rental_end_date=re, is_gift=gift, selected_pot_id=item.selected_pot_id)
            else:
                cls.add_item(user_cart, item.product, item.quantity, line_type=item.line_type, rental_billing=rb, rental_units=ru, rental_start_date=rs, rental_end_date=re, is_gift=gift, selected_pot_id=item.selected_pot_id)
        session_cart.status = Cart.Status.ABANDONED
        session_cart.save(update_fields=['status'])

    @staticmethod
    def merge_session_wishlist_to_user(request, user):
        if not user or not user.is_authenticated:
            return
        variant_ids = list(request.session.get('wishlist') or [])
        seen = set()
        for vid in variant_ids[:50]:
            try:
                vid = int(vid)
            except (TypeError, ValueError):
                continue
            if vid in seen:
                continue
            seen.add(vid)
            v = Variant.objects.filter(pk=vid, is_active=True, product__is_active=True).first()
            if not v:
                continue
            Wishlist.objects.get_or_create(user=user, selected_variant=v, defaults={'product': None})
        request.session.pop('wishlist', None)
        from ..wishlist_utils import GUEST_WISHLIST_PRODUCTS_KEY
        from ..models import Product
        from django.db.models import Count
        raw_pids = list(request.session.get(GUEST_WISHLIST_PRODUCTS_KEY) or [])
        seen_p = set()
        for pid in raw_pids[:50]:
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                continue
            if pid in seen_p:
                continue
            seen_p.add(pid)
            p = (
                Product.objects.filter(pk=pid, is_active=True)
                .annotate(_vc=Count('variants'))
                .filter(_vc=0)
                .first()
            )
            if not p:
                continue
            Wishlist.objects.get_or_create(user=user, product=p, defaults={'selected_variant': None})
        request.session.pop(GUEST_WISHLIST_PRODUCTS_KEY, None)

    @staticmethod
    def get_cart_stock_issues_for(cart):
        items = cart.items.select_related(
            'product', 'combo', 'selected_variant', 'selected_pot',
        ).prefetch_related('combo__items__product').all()
        return get_cart_stock_issues(items)

    @staticmethod
    def get_cart_delivery_issues_for(cart, state_id):
        items = cart.items.select_related(
            'product', 'combo', 'selected_variant', 'selected_pot',
        ).prefetch_related('combo__items__product').all()
        return get_cart_delivery_issues(items, state_id)

    @staticmethod
    def assert_cart_stock(cart):
        issues = CartService.get_cart_stock_issues_for(cart)
        if issues:
            raise StockError(format_cart_stock_error(issues))
        return issues

    @staticmethod
    def compute_totals(cart, state_id=None):
        """
        Cart totals. With no state_id, shipping is ₹0 (state must be selected
        at checkout). With a state_id, shipping is state charges × qty, or the
        flat fallback when no product charge rows exist for that state.
        """
        from .state_delivery_service import compute_cart_delivery_charges

        try:
            items = list(
                cart.items.select_related('product', 'combo', 'selected_variant')
                .prefetch_related('combo__items')
            )
            for item in items:
                if getattr(item, 'line_type', '') == 'rental':
                    continue
                updated = False
                if item.combo_id and item.combo:
                    if item.combo.price is not None and item.unit_price != item.combo.price:
                        item.unit_price = item.combo.price
                        updated = True
                elif getattr(item, 'selected_variant_id', None) and getattr(item, 'selected_variant', None):
                    if item.selected_variant.price is not None and item.unit_price != item.selected_variant.price:
                        item.unit_price = item.selected_variant.price
                        updated = True
                elif item.product_id and item.product:
                    if item.product.base_price is not None and item.unit_price != item.product.base_price:
                        item.unit_price = item.product.base_price
                        updated = True
                if updated:
                    item.save(update_fields=['unit_price'])

            subtotal = sum((item.line_total for item in items))
            gst_total = cart.gst_total
            breakdown = compute_cart_delivery_charges(items, state_id)
            shipping = breakdown.total
            total = subtotal + gst_total + shipping
            return CartTotals(
                subtotal=subtotal,
                gst_total=gst_total,
                shipping=shipping,
                total=total,
                delivery_breakdown=breakdown,
                used_flat_fallback=breakdown.used_flat_fallback,
                state_missing=breakdown.state_missing,
            )
        except Exception:
            return CartTotals(subtotal=0, gst_total=0, shipping=0, total=0, state_missing=True)

    @staticmethod
    def add_item(
        cart,
        sellable,
        quantity,
        *,
        line_type=CartItem.LineKind.PURCHASE,
        rental_billing=None,
        rental_units=None,
        rental_start_date=None,
        rental_end_date=None,
        is_gift=False,
        selected_pot_id=None
    ):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from ..models import Product
        from ..services.rental_pricing import compute_rental_line_unit_price, rental_key as make_rental_key
        from ..services.rental_catalog import combo_is_in_stock
        max_qty = getattr(settings, 'MAX_CART_QTY', 10)
        quantity = max(1, min(int(quantity), max_qty))
        gift_flag = bool(is_gift)

        # ── Pot addon validation ───────────────────────────────────────────────
        selected_pot = None
        pot_unit_price_val = None
        if selected_pot_id and line_type == CartItem.LineKind.PURCHASE:
            from ..models import Category as _Cat
            pot_cat_ids = list(
                _Cat.objects.filter(slug__in=['pot', 'pots'], is_active=True)
                .values_list('id', flat=True)
            )
            if pot_cat_ids:
                selected_pot = Product.objects.filter(
                    pk=int(selected_pot_id),
                    is_active=True,
                    category_id__in=pot_cat_ids,
                ).first()
                if not selected_pot:
                    raise CartError('Selected pot is not available.')
                if (selected_pot.base_stock or 0) <= 0:
                    raise StockError(f'"{selected_pot.name}" is out of stock.')
                if not selected_pot.base_price or selected_pot.base_price <= 0:
                    raise CartError(f'"{selected_pot.name}" does not have a valid price.')
                pot_unit_price_val = selected_pot.base_price

        rkey = ''
        unit_price = None
        rent_bill = ''
        rent_count = None
        if line_type == CartItem.LineKind.RENTAL:
            try:
                # Rentals are per-day in RentalConfig; accept legacy form fields but normalize to day.
                rent_bill = 'day'
                rent_count = int(rental_units)
            except (TypeError, ValueError):
                raise CartError('Invalid rental duration.') from None
            if rent_count is None or rent_count < 1:
                raise CartError('Select how many days to rent.')
            rkey = make_rental_key(rent_count)
            # Availability: rentals must be date-based in the platform.
            if not rental_start_date or not rental_end_date:
                raise CartError('Select rental start and end dates.')
            if rental_start_date and rental_end_date:
                from ..services.rental_availability import assert_available_for_rent
                try:
                    assert_available_for_rent(product=(sellable if isinstance(sellable, Product) else sellable.product), start=rental_start_date, end=rental_end_date)
                except DjangoValidationError as exc:
                    raise CartError('; '.join(getattr(exc, 'messages', [])) or str(exc)) from exc
        if isinstance(sellable, Product):
            product = sellable
            if product.has_variants():
                raise CartError('Invalid simple product. Variants exist for this product.')
            if line_type == CartItem.LineKind.PURCHASE:
                if not product.purchase_enabled:
                    raise CartError('This product is not available for purchase.')
                unit_price = product.base_price
                if unit_price is None or unit_price <= 0:
                    raise StockError('This item is not available for purchase.')
                if product.is_combo_product:
                    if not combo_is_in_stock(product, multiplier=quantity):
                        raise StockError('This item is out of stock.')
                else:
                    base_stock = product.base_stock or 0
                    if base_stock <= 0:
                        raise StockError('This item is out of stock.')
                    if quantity > base_stock:
                        raise StockError('Requested quantity exceeds available stock.')
                item = CartItem.objects.filter(cart=cart, product=product, selected_variant__isnull=True, line_type=line_type, rental_key=rkey, is_gift=gift_flag, selected_pot=selected_pot).first()
                if item:
                    new_quantity = min(item.quantity + quantity, max_qty)
                    if product.is_combo_product:
                        if not combo_is_in_stock(product, multiplier=new_quantity):
                            raise StockError('Requested quantity exceeds available stock.')
                    elif new_quantity > (product.base_stock or 0):
                        raise StockError('Requested quantity exceeds available stock.')
                    item.quantity = new_quantity
                    item.unit_price = unit_price
                    item.selected_pot = selected_pot
                    item.pot_unit_price = pot_unit_price_val
                    item.save(update_fields=['quantity', 'unit_price', 'selected_pot', 'pot_unit_price', 'updated_at'])
                    return item
                return CartItem.objects.create(cart=cart, product=product, selected_variant=None, quantity=quantity, unit_price=unit_price, line_type=line_type, rental_key=rkey, rental_billing_period=rent_bill, rental_period_count=rent_count, rental_start_date=rental_start_date, rental_end_date=rental_end_date, is_gift=gift_flag, selected_pot=selected_pot, pot_unit_price=pot_unit_price_val)
            try:
                unit_price = compute_rental_line_unit_price(product, days=rent_count)
            except DjangoValidationError as exc:
                raise CartError('; '.join(getattr(exc, 'messages', [])) or str(exc)) from exc
            if product.is_combo_product:
                if not combo_is_in_stock(product, multiplier=quantity):
                    raise StockError('This item is out of stock.')
            else:
                base_stock = product.base_stock or 0
                if base_stock <= 0 or quantity > base_stock:
                    raise StockError('Requested quantity exceeds available stock.')
            item = CartItem.objects.filter(cart=cart, product=product, selected_variant__isnull=True, line_type=line_type, rental_key=rkey, is_gift=gift_flag, rental_start_date=rental_start_date, rental_end_date=rental_end_date).first()
            if item:
                new_quantity = min(item.quantity + quantity, max_qty)
                if product.is_combo_product:
                    if not combo_is_in_stock(product, multiplier=new_quantity):
                        raise StockError('Requested quantity exceeds available stock.')
                elif new_quantity > (product.base_stock or 0):
                    raise StockError('Requested quantity exceeds available stock.')
                item.quantity = new_quantity
                item.unit_price = unit_price
                item.save(update_fields=['quantity', 'unit_price', 'updated_at'])
                return item
            return CartItem.objects.create(cart=cart, product=product, selected_variant=None, quantity=quantity, unit_price=unit_price, line_type=line_type, rental_key=rkey, rental_billing_period=rent_bill, rental_period_count=rent_count, rental_start_date=rental_start_date, rental_end_date=rental_end_date, is_gift=gift_flag)
        if not isinstance(sellable, Variant):
            raise CartError('Invalid sellable.')
        v = sellable
        product = v.product
        if getattr(product, 'is_combo_product', False):
            raise CartError('Invalid variant for combo product.')
        if line_type == CartItem.LineKind.PURCHASE:
            if not product.purchase_enabled:
                raise CartError('This product is not available for purchase.')
            if not getattr(v, 'is_active', True) or (v.stock_quantity or 0) <= 0:
                raise StockError('This item is out of stock.')
            if quantity > v.stock_quantity:
                raise StockError('Requested quantity exceeds available stock.')
            unit_price = v.price
            item = CartItem.objects.filter(cart=cart, selected_variant=v, line_type=line_type, rental_key=rkey, is_gift=gift_flag, selected_pot=selected_pot).first()
            if item:
                new_quantity = min(item.quantity + quantity, max_qty)
                if new_quantity > v.stock_quantity:
                    raise StockError('Requested quantity exceeds available stock.')
                item.quantity = new_quantity
                item.unit_price = unit_price
                item.selected_pot = selected_pot
                item.pot_unit_price = pot_unit_price_val
                item.save(update_fields=['quantity', 'unit_price', 'selected_pot', 'pot_unit_price', 'updated_at'])
                return item
            return CartItem.objects.create(cart=cart, product=product, selected_variant=v, quantity=quantity, unit_price=unit_price, line_type=line_type, rental_key=rkey, rental_billing_period=rent_bill, rental_period_count=rent_count, is_gift=gift_flag, selected_pot=selected_pot, pot_unit_price=pot_unit_price_val)
        if not getattr(v, 'is_active', True) or (v.stock_quantity or 0) <= 0:
            raise StockError('This item is out of stock.')
        if quantity > v.stock_quantity:
            raise StockError('Requested quantity exceeds available stock.')
        try:
            unit_price = compute_rental_line_unit_price(product, days=rent_count)
        except DjangoValidationError as exc:
            raise CartError('; '.join(getattr(exc, 'messages', []) or [str(exc)])) from exc
        item = CartItem.objects.filter(cart=cart, selected_variant=v, line_type=line_type, rental_key=rkey, is_gift=gift_flag, rental_start_date=rental_start_date, rental_end_date=rental_end_date).first()
        if item:
            new_quantity = min(item.quantity + quantity, max_qty)
            if new_quantity > v.stock_quantity:
                raise StockError('Requested quantity exceeds available stock.')
            item.quantity = new_quantity
            item.unit_price = unit_price
            item.save(update_fields=['quantity', 'unit_price', 'updated_at'])
            return item
        return CartItem.objects.create(cart=cart, product=product, selected_variant=v, quantity=quantity, unit_price=unit_price, line_type=line_type, rental_key=rkey, rental_billing_period=rent_bill, rental_period_count=rent_count, rental_start_date=rental_start_date, rental_end_date=rental_end_date, is_gift=gift_flag)

    @staticmethod
    def add_combo_item(cart, combo, quantity, *, line_type=CartItem.LineKind.PURCHASE, is_gift=False):
        from ..services.combo_catalog import combo_is_in_stock

        max_qty = getattr(settings, 'MAX_CART_QTY', 10)
        quantity = max(1, min(int(quantity), max_qty))
        if line_type != CartItem.LineKind.PURCHASE:
            raise CartError('Combo bundles can only be purchased (not rented).')
        if not isinstance(combo, Combo):
            combo = Combo.objects.filter(pk=int(combo), is_active=True).first()
            if not combo:
                raise CartError('Combo not found.')
        if not combo.is_active or not combo.purchase_enabled:
            raise CartError('This bundle is not available for purchase.')
        unit_price = combo.price
        if unit_price is None or unit_price <= 0:
            raise StockError('This item is not available for purchase.')
        if not combo_is_in_stock(combo, multiplier=quantity):
            raise StockError('This item is out of stock.')
        gift_flag = bool(is_gift)
        rkey = ''
        existing = CartItem.objects.filter(cart=cart, combo=combo, line_type=line_type, rental_key=rkey, is_gift=gift_flag).first()
        if existing:
            new_quantity = min(existing.quantity + quantity, max_qty)
            if not combo_is_in_stock(combo, multiplier=new_quantity):
                raise StockError('Requested quantity exceeds available stock.')
            existing.quantity = new_quantity
            existing.unit_price = unit_price
            existing.save(update_fields=['quantity', 'unit_price', 'updated_at'])
            return existing
        return CartItem.objects.create(
            cart=cart,
            combo=combo,
            product=None,
            selected_variant=None,
            quantity=quantity,
            unit_price=unit_price,
            line_type=line_type,
            rental_key=rkey,
            rental_billing_period='',
            rental_period_count=None,
            rental_start_date=None,
            rental_end_date=None,
            is_gift=gift_flag,
        )

    @staticmethod
    def update_item(item, quantity):
        from ..services.rental_catalog import combo_is_in_stock
        from ..services.combo_catalog import combo_is_in_stock as combo_bundle_in_stock
        if quantity <= 0:
            item.delete()
            return
        max_qty = getattr(settings, 'MAX_CART_QTY', 10)
        quantity = min(int(quantity), max_qty)
        if item.combo_id:
            c = item.combo
            if item.line_type == CartItem.LineKind.RENTAL:
                raise CartError('Invalid cart item.')
            if not combo_bundle_in_stock(c, multiplier=quantity):
                raise StockError('Requested quantity exceeds available stock.')
            item.quantity = quantity
            item.unit_price = c.price
            item.save(update_fields=['quantity', 'unit_price', 'updated_at'])
            return
        v = item.selected_variant
        product = item.product
        if item.line_type == CartItem.LineKind.RENTAL:
            if not v:
                if product.has_variants():
                    raise CartError('Invalid cart item.')
                if product.is_combo_product:
                    if not combo_is_in_stock(product, multiplier=quantity):
                        raise StockError('Requested quantity exceeds available stock.')
                elif quantity > (product.base_stock or 0):
                    raise StockError('Requested quantity exceeds available stock.')
            else:
                if quantity > (v.stock_quantity or 0):
                    raise StockError('Requested quantity exceeds available stock.')
            item.quantity = quantity
            item.save(update_fields=['quantity', 'updated_at'])
            return
        if not v:
            if product.has_variants():
                raise CartError('Invalid cart item.')
            if product.is_combo_product:
                if not combo_is_in_stock(product, multiplier=quantity):
                    raise StockError('Requested quantity exceeds available stock.')
            else:
                stock = product.base_stock or 0
                if quantity > stock:
                    raise StockError('Requested quantity exceeds available stock.')
            unit_price = product.base_price
        else:
            stock = v.stock_quantity
            if quantity > stock:
                raise StockError('Requested quantity exceeds available stock.')
            unit_price = v.price
        if item.line_type == CartItem.LineKind.PURCHASE and item.selected_pot_id:
            pot = getattr(item, 'selected_pot', None)
            if pot is None:
                pot = CartItem.objects.select_related('selected_pot').filter(pk=item.pk).values_list(
                    'selected_pot__base_stock', 'selected_pot__name'
                ).first()
                if pot:
                    pot_stock, pot_name = int(pot[0] or 0), pot[1]
                    if pot_stock <= 0:
                        raise StockError(f'Pot "{pot_name}" is out of stock.')
                    if quantity > pot_stock:
                        raise StockError(f'Only {pot_stock} pots available for "{pot_name}".')
            else:
                pot_stock = int(pot.base_stock or 0)
                if pot_stock <= 0:
                    raise StockError(f'Pot "{pot.name}" is out of stock.')
                if quantity > pot_stock:
                    raise StockError(f'Only {pot_stock} pots available for "{pot.name}".')
        item.quantity = quantity
        item.unit_price = unit_price
        item.save(update_fields=['quantity', 'unit_price', 'updated_at'])


class OrderService:

    @staticmethod
    def _generate_order_number():
        while True:
            order_number = f'QO{get_random_string(8).upper()}'
            if not Order.objects.filter(order_number=order_number).exists():
                return order_number

    @classmethod
    @transaction.atomic
    def create_order(cls, cart, form_data, user=None, clear_cart=True):
        if cart.status != Cart.Status.ACTIVE:
            raise CartError('This cart has already been used for an order.')
        items = (
            cart.items.select_related('selected_variant', 'product', 'combo', 'selected_pot')
            .prefetch_related('combo__items__product')
            .select_for_update(of=('self',))
            .all()
        )
        if not items:
            raise CartError('Cart is empty.')
        issues = get_cart_stock_issues(items)
        if issues:
            raise StockError(format_cart_stock_error(issues))

        from .state_delivery_service import resolve_delivery_state_id

        selected_address_id = form_data.get('selected_address')
        use_new_address = form_data.get('use_new_address', False)
        state_id = resolve_delivery_state_id(
            delivery_state=form_data.get('delivery_state'),
            state_text=form_data.get('state', ''),
        )
        if selected_address_id and (not use_new_address) and user and not state_id:
            try:
                existing_address = Address.objects.get(pk=selected_address_id, user=user, is_snapshot=False)
                state_id = resolve_delivery_state_id(
                    delivery_state=existing_address.delivery_state,
                    state_text=existing_address.state,
                )
            except Address.DoesNotExist:
                pass
        delivery_issues = get_cart_delivery_issues(items, state_id)
        if delivery_issues:
            raise CartError(format_cart_delivery_error(delivery_issues))

        if selected_address_id and (not use_new_address) and user:
            try:
                existing_address = Address.objects.get(pk=selected_address_id, user=user, is_snapshot=False)
                address = Address.objects.create(
                    user=user,
                    full_name=existing_address.full_name,
                    phone=existing_address.phone,
                    email=existing_address.email,
                    address_line=existing_address.address_line,
                    city=existing_address.city,
                    state=existing_address.state,
                    pincode=existing_address.pincode,
                    delivery_state=existing_address.delivery_state,
                    is_snapshot=True,
                )
            except Address.DoesNotExist:
                raise CartError('Selected address not found.')
        else:
            user_obj = user if user is not None else cart.user
            full_name = form_data['full_name']
            phone = form_data['phone']
            email = form_data.get('email', '')
            address_line = form_data['address_line']
            city = form_data['city']
            state = form_data['state']
            pincode = form_data['pincode']
            delivery_state = form_data.get('delivery_state')
            delivery_state_id = delivery_state.pk if hasattr(delivery_state, 'pk') else delivery_state
            address_kwargs = dict(
                full_name=full_name,
                phone=phone,
                email=email,
                address_line=address_line,
                city=city,
                state=state,
                pincode=pincode,
            )
            if delivery_state_id:
                address_kwargs['delivery_state_id'] = delivery_state_id
            if user_obj:
                has_any_saved = Address.objects.filter(user=user_obj, is_snapshot=False).exists()
                saved_address = Address.objects.create(
                    user=user_obj,
                    is_default=not has_any_saved,
                    is_snapshot=False,
                    **address_kwargs,
                )
                address = Address.objects.create(
                    user=user_obj,
                    full_name=saved_address.full_name,
                    phone=saved_address.phone,
                    email=saved_address.email,
                    address_line=saved_address.address_line,
                    city=saved_address.city,
                    state=saved_address.state,
                    pincode=saved_address.pincode,
                    delivery_state=saved_address.delivery_state,
                    is_snapshot=True,
                )
            else:
                address = Address.objects.create(user=None, is_snapshot=True, **address_kwargs)
        # Rental bookings require dates; prevent checkout if rental lines missing dates.
        for it in items:
            if it.line_type == CartItem.LineKind.RENTAL and (not it.rental_start_date or not it.rental_end_date):
                raise CartError('Please select rental start and end dates for rental items in your cart.')

        delivery_state_id = resolve_delivery_state_id(
            delivery_state=address.delivery_state,
            state_text=address.state,
        )
        delivery_state_name = ''
        if address.delivery_state_id and address.delivery_state:
            delivery_state_name = address.delivery_state.name
        elif address.state:
            delivery_state_name = address.state

        totals = CartService.compute_totals(cart, state_id=delivery_state_id)
        order_number = cls._generate_order_number()
        gst_total = getattr(totals, 'gst_total', 0) or 0
        state = (address.state or '').strip()
        if (delivery_state_name or state).lower() == 'kerala':
            cgst = gst_total / 2
            sgst = gst_total / 2
            igst = 0
        else:
            cgst = 0
            sgst = 0
            igst = gst_total

        from decimal import Decimal

        from .coupon_service import CouponError, record_redemption, validate_for_checkout

        discount_amount = Decimal('0')
        coupon_obj = None
        coupon_code_snap = ''
        raw_coupon = (form_data.get('coupon_code') or '').strip()
        if raw_coupon:
            try:
                validated = validate_for_checkout(
                    raw_coupon,
                    subtotal=totals.subtotal,
                    user=user or cart.user,
                    email=address.email or form_data.get('email', ''),
                    phone=address.phone or form_data.get('phone', ''),
                )
            except CouponError as exc:
                raise CartError(exc.message) from exc
            discount_amount = validated.discount_amount
            coupon_obj = validated.coupon
            coupon_code_snap = validated.code

        payable = (
            (totals.subtotal or 0)
            + (gst_total or 0)
            + (totals.shipping or 0)
            - discount_amount
        )

        order = Order.objects.create(
            user=cart.user if cart.user else None,
            order_number=order_number,
            subtotal=totals.subtotal,
            shipping=totals.shipping,
            delivery_state_name=delivery_state_name,
            gst_total=gst_total,
            cgst=cgst,
            sgst=sgst,
            igst=igst,
            coupon=coupon_obj,
            coupon_code=coupon_code_snap,
            discount_amount=discount_amount,
            total=payable,
            address=address,
        )

        if coupon_obj:
            record_redemption(
                order,
                coupon_obj,
                discount_amount,
                user=order.user,
                email=address.email or '',
                phone=address.phone or '',
            )

        def _line_delivery(item):
            # Delivery charge is a pooled cart-wide total (see compute_cart_delivery_charges),
            # not attributable to a single line — order.shipping holds the real amount.
            return Decimal('0'), Decimal('0')

        for item in items:
            per_unit, line_delivery = _line_delivery(item)
            if item.combo_id:
                c = item.combo
                comp_parts = []
                for row in c.items.all():
                    comp_parts.append(f'{row.product.name} × {row.quantity}')
                snapshot = 'Bundle: ' + '; '.join(comp_parts) if comp_parts else 'Bundle'
                rental_snap = ''
                taxable_value = 0
                gst_amount = 0
                hsn_code = None
                gst_percentage = None
                if getattr(c, 'is_gst_applicable', False) and getattr(c, 'gst_percentage', None) is not None:
                    taxable_value = item.unit_price * item.quantity
                    gst_amount = taxable_value * (c.gst_percentage / Decimal('100'))
                    hsn_code = getattr(c, 'hsn_code', None) or None
                    gst_percentage = c.gst_percentage
                snap = snapshot or c.name
                order_item = OrderItem.objects.create(
                    order=order,
                    product=None,
                    combo=c,
                    selected_variant=None,
                    product_name=c.name,
                    variant_snapshot=snap[:255],
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    line_type=item.line_type,
                    rental_key=item.rental_key or '',
                    rental_billing_period=item.rental_billing_period or '',
                    rental_period_count=item.rental_period_count,
                    rental_snapshot=rental_snap,
                    rental_start_date=item.rental_start_date,
                    rental_end_date=item.rental_end_date,
                    hsn_code=hsn_code,
                    gst_percentage=gst_percentage,
                    taxable_value=taxable_value,
                    gst_amount=gst_amount,
                    is_gift=item.is_gift,
                    selected_pot_name=(item.selected_pot.name if item.selected_pot_id and item.selected_pot else ''),
                    pot_unit_price=item.pot_unit_price,
                    delivery_charge_per_unit=per_unit,
                    total_delivery_charge=line_delivery,
                )
                if form_data.get('payment') != Payment.Method.RAZORPAY:
                    decrement_stock_for_order_item(order_item)
                continue

            v = item.selected_variant
            product = item.product
            snapshot = v.get_attribute_values_display() if v else 'Default'
            rental_snap = item.rental_label() if item.line_type == CartItem.LineKind.RENTAL else ''
            if rental_snap:
                snapshot = f'{snapshot} · {rental_snap}' if snapshot else rental_snap
            taxable_value = 0
            gst_amount = 0
            hsn_code = None
            gst_percentage = None
            if getattr(product, 'is_gst_applicable', False) and getattr(product, 'gst_percentage', None) is not None:
                line_base = item.unit_price + (item.pot_unit_price or 0)
                taxable_value = line_base * item.quantity
                gst_amount = taxable_value * (product.gst_percentage / Decimal('100'))
                hsn_code = getattr(product, 'hsn_code', None) or None
                gst_percentage = product.gst_percentage
            snap = snapshot or product.name
            if item.selected_pot_id and item.selected_pot:
                snap = f'{snap} + {item.selected_pot.name}'
            order_item = OrderItem.objects.create(
                order=order,
                product=product,
                combo=None,
                selected_variant=v,
                product_name=product.name,
                variant_snapshot=snap,
                unit_price=item.unit_price,
                quantity=item.quantity,
                line_type=item.line_type,
                rental_key=item.rental_key or '',
                rental_billing_period=item.rental_billing_period or '',
                rental_period_count=item.rental_period_count,
                rental_snapshot=rental_snap,
                rental_start_date=item.rental_start_date,
                rental_end_date=item.rental_end_date,
                hsn_code=hsn_code,
                gst_percentage=gst_percentage,
                taxable_value=taxable_value,
                gst_amount=gst_amount,
                is_gift=item.is_gift,
                selected_pot_name=item.selected_pot.name if item.selected_pot_id else '',
                pot_unit_price=item.pot_unit_price,
                delivery_charge_per_unit=per_unit,
                total_delivery_charge=line_delivery,
            )
            # Create rental booking for lifecycle management
            if item.line_type == CartItem.LineKind.RENTAL:
                from ..models import RentalBooking
                from ..services.rental_availability import assert_available_for_rent
                if not item.rental_start_date or not item.rental_end_date:
                    raise CartError('Rental dates are required for rental bookings.')
                assert_available_for_rent(product=product, start=item.rental_start_date, end=item.rental_end_date)
                cfg = getattr(product, 'rental_config', None)
                price_per_day = getattr(cfg, 'rent_price_per_day', None) if cfg else None
                if price_per_day is None:
                    raise CartError('Rental pricing is not configured for this product.')
                total_days = int(item.rental_period_count or 0) or ((item.rental_end_date - item.rental_start_date).days + 1)
                total_amount = item.unit_price * item.quantity
                RentalBooking.objects.create(
                    user=order.user,
                    product=product,
                    order_item=order_item,
                    rental_start_date=item.rental_start_date,
                    rental_end_date=item.rental_end_date,
                    total_days=total_days,
                    price_per_day=price_per_day,
                    total_amount=total_amount,
                    status=RentalBooking.Status.PENDING,
                )
            if form_data.get('payment') != Payment.Method.RAZORPAY:
                decrement_stock_for_order_item(order_item)
        Payment.objects.create(order=order, method=form_data.get('payment', Payment.Method.COD), amount=order.total)
        if clear_cart:
            cart.status = Cart.Status.ORDERED
            cart.save(update_fields=['status'])
            cart.items.all().delete()
        send_order_notification_email_async(order)
        return order
