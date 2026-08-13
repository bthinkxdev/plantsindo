"""
Unit tests for CouponService, checkout totals discount, and order redemption.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from app.models import (
    Cart,
    CartItem,
    Category,
    Coupon,
    CouponRedemption,
    DeliveryState,
    Product,
)
from app.services import coupon_service
from app.services.cart_order import CartError, OrderService, resolve_checkout_totals
from app.services.state_delivery_service import set_product_delivery_states, set_state_delivery_charges


User = get_user_model()
ZERO = Decimal('0.00')


class CouponServiceMathTests(TestCase):
    def setUp(self):
        self.percent = Coupon.objects.create(
            code='SAVE10',
            discount_type=Coupon.DiscountType.PERCENT,
            value=Decimal('10'),
            max_discount_amount=Decimal('50'),
        )
        self.fixed = Coupon.objects.create(
            code='FLAT100',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('100'),
            min_order_amount=Decimal('200'),
        )

    def test_percent_discount(self):
        self.assertEqual(
            coupon_service.compute_discount(self.percent, Decimal('400')),
            Decimal('40.00'),
        )

    def test_percent_capped_by_max_discount(self):
        self.assertEqual(
            coupon_service.compute_discount(self.percent, Decimal('1000')),
            Decimal('50.00'),
        )

    def test_fixed_discount(self):
        self.assertEqual(
            coupon_service.compute_discount(self.fixed, Decimal('500')),
            Decimal('100.00'),
        )

    def test_discount_never_exceeds_subtotal(self):
        big = Coupon.objects.create(
            code='HUGE',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('999'),
        )
        self.assertEqual(
            coupon_service.compute_discount(big, Decimal('80')),
            Decimal('80.00'),
        )

    def test_min_order_blocks_compute(self):
        self.assertEqual(
            coupon_service.compute_discount(self.fixed, Decimal('150')),
            ZERO,
        )

    def test_validate_min_order_raises(self):
        with self.assertRaises(coupon_service.CouponError) as ctx:
            coupon_service.validate_for_checkout(
                'FLAT100', subtotal=Decimal('150')
            )
        self.assertEqual(ctx.exception.code, 'min_order')


class CouponValidityTests(TestCase):
    def test_inactive(self):
        Coupon.objects.create(
            code='OFF',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('10'),
            is_active=False,
        )
        with self.assertRaises(coupon_service.CouponError) as ctx:
            coupon_service.validate_for_checkout('OFF', subtotal=Decimal('100'))
        self.assertEqual(ctx.exception.code, 'inactive')

    def test_not_started(self):
        Coupon.objects.create(
            code='SOON',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('10'),
            starts_at=timezone.now() + timedelta(days=1),
        )
        with self.assertRaises(coupon_service.CouponError) as ctx:
            coupon_service.validate_for_checkout('SOON', subtotal=Decimal('100'))
        self.assertEqual(ctx.exception.code, 'not_started')

    def test_expired(self):
        Coupon.objects.create(
            code='OLD',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('10'),
            ends_at=timezone.now() - timedelta(hours=1),
        )
        with self.assertRaises(coupon_service.CouponError) as ctx:
            coupon_service.validate_for_checkout('OLD', subtotal=Decimal('100'))
        self.assertEqual(ctx.exception.code, 'expired')

    def test_global_max_uses_exhausted(self):
        c = Coupon.objects.create(
            code='ONCE',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('10'),
            max_uses=1,
            times_redeemed=1,
        )
        with self.assertRaises(coupon_service.CouponError) as ctx:
            coupon_service.validate_for_checkout('ONCE', subtotal=Decimal('100'))
        self.assertEqual(ctx.exception.code, 'exhausted')
        self.assertFalse(coupon_service.is_currently_valid(c)[0])


@override_settings(FLAT_DELIVERY_CHARGE=60, DELIVERY_PACK_SIZE=2)
class CouponCheckoutAndOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(name='Plants', slug='plants-c', is_active=True)
        cls.kerala = DeliveryState.objects.create(
            name='Kerala', code='KL-C', region='south', display_order=0, is_active=True,
        )
        cls.product = Product.objects.create(
            name='Aloe',
            slug='aloe-c',
            category=cls.cat,
            base_price=Decimal('200.00'),
            base_stock=50,
            is_active=True,
        )
        set_state_delivery_charges({cls.kerala.pk: Decimal('50')})
        set_product_delivery_states(cls.product.pk, [cls.kerala.pk])

    def _cart(self, user=None, qty=2):
        cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=qty,
        )
        return cart

    def _form(self, coupon_code='', payment='cod', email='buyer@example.com'):
        return {
            'full_name': 'Buyer',
            'phone': '9999999999',
            'email': email,
            'address_line': 'Line 1',
            'city': 'Kochi',
            'state': 'Kerala',
            'pincode': '682001',
            'delivery_state': self.kerala,
            'payment': payment,
            'use_new_address': True,
            'coupon_code': coupon_code,
        }

    def test_resolve_checkout_totals_includes_discount(self):
        Coupon.objects.create(
            code='TEN',
            discount_type=Coupon.DiscountType.PERCENT,
            value=Decimal('10'),
        )
        cart = self._cart(qty=2)  # subtotal 400
        result = resolve_checkout_totals(
            cart,
            state_id=self.kerala.pk,
            coupon_code='TEN',
            email='buyer@example.com',
        )
        self.assertEqual(result.discount_amount, Decimal('40.00'))
        self.assertEqual(result.coupon_code, 'TEN')
        # shipping = ceil(2/2)*50 = 50; total = 400 + gst + 50 - 40
        expected = (
            result.subtotal + result.gst_total + result.shipping - result.discount_amount
        )
        self.assertEqual(result.total, expected)
        self.assertEqual(str(result.discount_amount), '40.00')
        self.assertEqual(result.coupon_code, 'TEN')

    def test_create_order_persists_discount_and_redemption_cod(self):
        coupon = Coupon.objects.create(
            code='COD10',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('50'),
            max_uses_per_customer=1,
        )
        user = User.objects.create_user(username='c1', email='c1@example.com', password='x')
        cart = self._cart(user=user, qty=2)
        order = OrderService.create_order(
            cart, self._form('COD10', payment='cod', email='c1@example.com'), user=user
        )
        self.assertEqual(order.discount_amount, Decimal('50.00'))
        self.assertEqual(order.coupon_code, 'COD10')
        self.assertEqual(order.coupon_id, coupon.pk)
        expected_total = order.subtotal + order.gst_total + order.shipping - order.discount_amount
        self.assertEqual(order.total, expected_total)
        self.assertEqual(order.payment.amount, order.total)
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_redeemed, 1)
        self.assertTrue(CouponRedemption.objects.filter(order=order, coupon=coupon).exists())

    def test_per_customer_limit_blocks_second_use(self):
        Coupon.objects.create(
            code='ONCEME',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('20'),
            max_uses_per_customer=1,
        )
        user = User.objects.create_user(username='c2', email='c2@example.com', password='x')
        cart1 = self._cart(user=user, qty=2)
        OrderService.create_order(
            cart1, self._form('ONCEME', email='c2@example.com'), user=user
        )
        cart2 = self._cart(user=user, qty=2)
        with self.assertRaises(CartError):
            OrderService.create_order(
                cart2, self._form('ONCEME', email='c2@example.com'), user=user
            )

    def test_guest_email_customer_limit(self):
        Coupon.objects.create(
            code='GUEST1',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('20'),
            max_uses_per_customer=1,
        )
        cart1 = self._cart(qty=2)
        OrderService.create_order(
            cart1, self._form('GUEST1', email='guest@example.com'), user=None
        )
        cart2 = self._cart(qty=2)
        with self.assertRaises(CartError):
            OrderService.create_order(
                cart2, self._form('GUEST1', email='guest@example.com'), user=None
            )

    def test_razorpay_path_uses_discounted_total(self):
        Coupon.objects.create(
            code='RZPAY',
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal('75'),
        )
        user = User.objects.create_user(username='rz', email='rz@example.com', password='x')
        cart = self._cart(user=user, qty=2)
        order = OrderService.create_order(
            cart,
            self._form('RZPAY', payment='razorpay', email='rz@example.com'),
            user=user,
        )
        expected = order.subtotal + order.gst_total + order.shipping - Decimal('75.00')
        self.assertEqual(order.total, expected)
        self.assertEqual(order.payment.amount, order.total)
        self.assertEqual(order.discount_amount, Decimal('75.00'))
