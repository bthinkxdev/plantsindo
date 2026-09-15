"""
Tests for state-based delivery charges.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from app.admin_forms import ProductDeliveryStateForm, StateDeliveryChargeForm
from app.models import (
    Cart,
    CartItem,
    Category,
    DeliveryState,
    Product,
)
from app.services.cart_order import CartService
from app.services.state_delivery_service import (
    billed_kg,
    cart_total_weight,
    compute_cart_delivery_charges,
    delivery_weight_upsell_message,
    get_product_delivery_charge,
    get_state_delivery_charge,
    set_product_delivery_states,
    set_state_delivery_charges,
)


User = get_user_model()


@override_settings(FLAT_DELIVERY_CHARGE=60, DELIVERY_MIN_BILLABLE_KG=1)
class StateDeliveryChargeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(name='Plants', slug='plants', is_active=True)
        cls.kerala = DeliveryState.objects.create(
            name='Kerala', code='KL', region='south', display_order=0, is_active=True,
        )
        cls.tn = DeliveryState.objects.create(
            name='Tamil Nadu', code='TN', region='south', display_order=1, is_active=True,
        )
        cls.ka = DeliveryState.objects.create(
            name='Karnataka', code='KA', region='south', display_order=2, is_active=True,
        )
        cls.product = Product.objects.create(
            name='Snake Plant',
            slug='snake-plant',
            category=cls.cat,
            base_price=Decimal('200.00'),
            base_stock=50,
            weight=Decimal('0.500'),
            is_active=True,
        )

    def test_set_state_delivery_charges_is_centralized(self):
        """Charge is per state (₹/kg), applies to every product that ships there."""
        set_state_delivery_charges({self.kerala.pk: Decimal('50'), self.tn.pk: Decimal('80')})
        set_product_delivery_states(self.product.pk, [self.kerala.pk, self.tn.pk])

        self.assertEqual(get_state_delivery_charge(self.kerala.pk), Decimal('50'))
        self.assertEqual(get_product_delivery_charge(self.product.pk, self.kerala.pk), Decimal('50'))
        self.assertEqual(get_product_delivery_charge(self.product.pk, self.tn.pk), Decimal('80'))
        # Product doesn't ship to Karnataka.
        self.assertIsNone(get_product_delivery_charge(self.product.pk, self.ka.pk))

    def test_product_delivery_state_form_only_selects_states(self):
        form = ProductDeliveryStateForm(
            data={'states': [str(self.kerala.pk), str(self.tn.pk)]},
            product=self.product,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(
            set(self.product.delivery_states.values_list('state_id', flat=True)),
            {self.kerala.pk, self.tn.pk},
        )

    def test_state_charge_form_rejects_negative_charge(self):
        form = StateDeliveryChargeForm(data={f'charge_{self.kerala.pk}': '-10'})
        self.assertFalse(form.is_valid())

    def test_state_charge_form_saves_charges(self):
        form = StateDeliveryChargeForm(data={
            f'charge_{self.kerala.pk}': '50',
            f'charge_{self.tn.pk}': '80',
            f'charge_{self.ka.pk}': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.kerala.refresh_from_db()
        self.tn.refresh_from_db()
        self.ka.refresh_from_db()
        self.assertEqual(self.kerala.delivery_charge, Decimal('50'))
        self.assertEqual(self.tn.delivery_charge, Decimal('80'))
        self.assertIsNone(self.ka.delivery_charge)

    def test_compute_totals_multiplies_charge_by_billed_kg(self):
        set_state_delivery_charges({self.kerala.pk: Decimal('50')})
        set_product_delivery_states(self.product.pk, [self.kerala.pk])
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=3,
        )
        totals = CartService.compute_totals(cart, state_id=self.kerala.pk)
        # 3 x 0.5kg = 1.5kg -> ceil = 2kg billed x ₹50
        self.assertEqual(totals.shipping, Decimal('100'))
        self.assertFalse(totals.used_flat_fallback)
        self.assertEqual(totals.total, Decimal('200') * 3 + Decimal('100'))

    def test_qty_one_and_two_share_same_kg_charge(self):
        """0.5kg x 1 and 0.5kg x 2 both round up to the same 1kg minimum."""
        set_state_delivery_charges({self.kerala.pk: Decimal('80')})
        set_product_delivery_states(self.product.pk, [self.kerala.pk])
        cart1 = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(
            cart=cart1,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=1,
        )
        cart2 = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(
            cart=cart2,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=2,
        )
        t1 = CartService.compute_totals(cart1, state_id=self.kerala.pk)
        t2 = CartService.compute_totals(cart2, state_id=self.kerala.pk)
        self.assertEqual(t1.shipping, Decimal('80'))
        self.assertEqual(t2.shipping, Decimal('80'))
        self.assertEqual(t1.shipping, t2.shipping)

    def test_minimum_one_kg_billed_even_for_light_single_item(self):
        light = Product.objects.create(
            name='Succulent', slug='succulent', category=self.cat,
            base_price=Decimal('50.00'), base_stock=20, weight=Decimal('0.050'), is_active=True,
        )
        set_state_delivery_charges({self.kerala.pk: Decimal('50')})
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=light, unit_price=light.base_price, quantity=1)
        totals = CartService.compute_totals(cart, state_id=self.kerala.pk)
        # 0.05kg still bills the 1kg minimum, not a fraction.
        self.assertEqual(totals.shipping, Decimal('50'))
        self.assertFalse(totals.used_flat_fallback)

    def test_flat_fallback_when_no_state_charge_configured(self):
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=2,
        )
        totals = CartService.compute_totals(cart, state_id=self.kerala.pk)
        self.assertEqual(totals.shipping, Decimal('60'))
        self.assertTrue(totals.used_flat_fallback)

    def test_flat_fallback_when_product_weight_not_configured(self):
        """A state rate alone isn't enough — an unweighed line must never be silently under-charged."""
        unweighed = Product.objects.create(
            name='No Weight Plant', slug='no-weight-plant', category=self.cat,
            base_price=Decimal('150.00'), base_stock=10, is_active=True,
        )
        self.assertEqual(unweighed.weight, Decimal('0'))
        set_state_delivery_charges({self.kerala.pk: Decimal('50')})
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=unweighed, unit_price=unweighed.base_price, quantity=1)
        totals = CartService.compute_totals(cart, state_id=self.kerala.pk)
        self.assertEqual(totals.shipping, Decimal('60'))
        self.assertTrue(totals.used_flat_fallback)

    def test_no_shipping_without_state_id(self):
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=1,
        )
        totals = CartService.compute_totals(cart, state_id=None)
        self.assertEqual(totals.shipping, Decimal('0'))
        self.assertTrue(totals.state_missing)

    def test_checkout_totals_api_requires_state(self):
        client = Client()
        session = client.session
        session.save()
        cart = Cart.objects.create(
            session_key=session.session_key,
            status=Cart.Status.ACTIVE,
        )
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=1,
        )
        url = reverse('store:checkout_totals')
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['state_missing'])
        self.assertEqual(payload['shipping_label'], 'Please select the state')
        self.assertEqual(Decimal(payload['shipping']), Decimal('0'))
        self.assertTrue(payload['checkout_blocked'])

    def test_checkout_totals_api_unavailable_state(self):
        set_state_delivery_charges({self.kerala.pk: Decimal('50')})
        set_product_delivery_states(self.product.pk, [self.kerala.pk])
        client = Client()
        session = client.session
        session.save()
        cart = Cart.objects.create(
            session_key=session.session_key,
            status=Cart.Status.ACTIVE,
        )
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=1,
        )
        url = reverse('store:checkout_totals')
        response = client.get(url, {'state_id': self.tn.pk})
        payload = response.json()
        self.assertFalse(payload['serviceable'])
        self.assertEqual(payload['status'], 'unavailable')
        self.assertEqual(Decimal(payload['shipping']), Decimal('0'))
        self.assertTrue(payload['checkout_blocked'])
        self.assertIn('Not deliverable in', payload['delivery_message'])
        self.assertIn('Tamil Nadu', payload['delivery_message'])

    def test_checkout_totals_api_ok(self):
        set_state_delivery_charges({self.tn.pk: Decimal('80')})
        set_product_delivery_states(self.product.pk, [self.tn.pk])
        client = Client()
        session = client.session
        session.save()
        cart = Cart.objects.create(
            session_key=session.session_key,
            status=Cart.Status.ACTIVE,
        )
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=2,
        )
        url = reverse('store:checkout_totals')
        response = client.get(url, {'state_id': self.tn.pk})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertTrue(payload['serviceable'])
        self.assertEqual(payload['status'], 'ok')
        # 2 x 0.5kg = 1kg -> billed 1kg x ₹80
        self.assertEqual(Decimal(payload['shipping']), Decimal('80'))
        self.assertFalse(payload['checkout_blocked'])

    def test_order_persists_delivery_snapshot_at_order_level(self):
        set_state_delivery_charges({self.kerala.pk: Decimal('50')})
        set_product_delivery_states(self.product.pk, [self.kerala.pk])
        from app.models import Address
        from app.services.cart_order import OrderService

        user = User.objects.create_user(username='buyer', email='b@example.com', password='x')
        cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            unit_price=self.product.base_price,
            quantity=3,
        )
        form_data = {
            'full_name': 'Buyer',
            'phone': '9999999999',
            'email': 'b@example.com',
            'address_line': 'Line 1',
            'city': 'Kochi',
            'state': 'Kerala',
            'pincode': '682001',
            'delivery_state': self.kerala,
            'payment': 'cod',
            'use_new_address': True,
        }
        order = OrderService.create_order(cart, form_data, user=user, clear_cart=True)
        # 3 x 0.5kg = 1.5kg -> ceil = 2kg billed x ₹50, carried entirely at the order level.
        self.assertEqual(order.shipping, Decimal('100'))
        self.assertEqual(order.delivery_state_name, 'Kerala')
        self.assertEqual(order.total_delivery_charge, Decimal('100'))
        item = order.items.get()
        self.assertEqual(item.delivery_charge_per_unit, Decimal('0'))
        self.assertEqual(item.total_delivery_charge, Decimal('0'))
        self.assertEqual(item.line_grand_total, item.line_total)

        # Later central charge change must not affect the persisted order.
        set_state_delivery_charges({self.kerala.pk: Decimal('999')})
        order.refresh_from_db()
        self.assertEqual(order.shipping, Decimal('100'))


class CartDeliveryBreakdownUnitTests(TestCase):
    def test_breakdown_pools_weight_across_products(self):
        """Two different products' weight pools into one cart-wide total, same as one product carrying the combined weight."""
        cat = Category.objects.create(name='C', slug='c', is_active=True)
        kl = DeliveryState.objects.create(name='Kerala', code='KL2', region='south', display_order=0)
        kl.delivery_charge = Decimal('50')
        kl.save(update_fields=['delivery_charge'])
        p1 = Product.objects.create(name='P1', slug='p1', category=cat, base_price=100, base_stock=10, weight=Decimal('0.500'), is_active=True)
        p2 = Product.objects.create(name='P2', slug='p2', category=cat, base_price=100, base_stock=10, weight=Decimal('0.500'), is_active=True)
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        i1 = CartItem.objects.create(cart=cart, product=p1, unit_price=100, quantity=1)
        i2 = CartItem.objects.create(cart=cart, product=p2, unit_price=100, quantity=1)
        breakdown = compute_cart_delivery_charges(list(cart.items.all()), kl.pk)
        # Pooled: 0.5kg + 0.5kg = 1kg -> billed 1kg x ₹50, not two separate minimums.
        self.assertEqual(breakdown.total, Decimal('50'))
        self.assertFalse(breakdown.used_flat_fallback)
        # Per-line charges aren't attributable — the pooled total lives at the order level.
        self.assertEqual(breakdown.line_for(i1.id)['total_delivery_charge'], Decimal('0'))
        self.assertEqual(breakdown.line_for(i2.id)['total_delivery_charge'], Decimal('0'))

    def test_extra_weight_bills_extra_kg(self):
        cat = Category.objects.create(name='C2', slug='c2', is_active=True)
        kl = DeliveryState.objects.create(name='Kerala', code='KL3', region='south', display_order=0)
        kl.delivery_charge = Decimal('50')
        kl.save(update_fields=['delivery_charge'])
        p1 = Product.objects.create(name='P3', slug='p3', category=cat, base_price=100, base_stock=10, weight=Decimal('0.500'), is_active=True)
        p2 = Product.objects.create(name='P4', slug='p4', category=cat, base_price=100, base_stock=10, weight=Decimal('0.500'), is_active=True)
        p3 = Product.objects.create(name='P5', slug='p5', category=cat, base_price=100, base_stock=10, weight=Decimal('0.500'), is_active=True)
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=p1, unit_price=100, quantity=1)
        CartItem.objects.create(cart=cart, product=p2, unit_price=100, quantity=1)
        CartItem.objects.create(cart=cart, product=p3, unit_price=100, quantity=1)
        breakdown = compute_cart_delivery_charges(list(cart.items.all()), kl.pk)
        # 3 x 0.5kg = 1.5kg -> ceil = 2kg billed x ₹50
        self.assertEqual(breakdown.total, Decimal('100'))

    def test_combo_weight_sums_component_quantities(self):
        from app.models import Combo, ComboItem

        cat = Category.objects.create(name='C3', slug='c3', is_active=True)
        kl = DeliveryState.objects.create(name='Kerala', code='KL4', region='south', display_order=0)
        kl.delivery_charge = Decimal('50')
        kl.save(update_fields=['delivery_charge'])
        p1 = Product.objects.create(name='CP1', slug='cp1', category=cat, base_price=100, base_stock=10, weight=Decimal('0.400'), is_active=True)
        p2 = Product.objects.create(name='CP2', slug='cp2', category=cat, base_price=100, base_stock=10, weight=Decimal('0.300'), is_active=True)
        combo = Combo.objects.create(name='Bundle', slug='bundle', price=Decimal('300'), is_active=True)
        ComboItem.objects.create(combo=combo, product=p1, quantity=2)  # 0.8kg
        ComboItem.objects.create(combo=combo, product=p2, quantity=1)  # 0.3kg
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, combo=combo, unit_price=combo.price, quantity=1)
        breakdown = compute_cart_delivery_charges(list(cart.items.all()), kl.pk)
        # combo unit weight = 0.8kg + 0.3kg = 1.1kg -> ceil = 2kg billed x ₹50
        self.assertEqual(breakdown.total, Decimal('100'))


class CartTotalWeightTests(TestCase):
    def test_flags_unweighted_line(self):
        cat = Category.objects.create(name='C4', slug='c4', is_active=True)
        weighed = Product.objects.create(name='W1', slug='w1', category=cat, base_price=100, base_stock=10, weight=Decimal('0.500'), is_active=True)
        unweighed = Product.objects.create(name='W2', slug='w2', category=cat, base_price=100, base_stock=10, is_active=True)
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=weighed, unit_price=100, quantity=1)
        CartItem.objects.create(cart=cart, product=unweighed, unit_price=100, quantity=1)
        total, has_unweighted = cart_total_weight(list(cart.items.all()))
        self.assertEqual(total, Decimal('0.500'))
        self.assertTrue(has_unweighted)

    def test_no_unweighted_flag_when_every_line_has_weight(self):
        cat = Category.objects.create(name='C5', slug='c5', is_active=True)
        p1 = Product.objects.create(name='W3', slug='w3', category=cat, base_price=100, base_stock=10, weight=Decimal('0.500'), is_active=True)
        p2 = Product.objects.create(name='W4', slug='w4', category=cat, base_price=100, base_stock=10, weight=Decimal('0.250'), is_active=True)
        cart = Cart.objects.create(status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=p1, unit_price=100, quantity=2)
        CartItem.objects.create(cart=cart, product=p2, unit_price=100, quantity=1)
        total, has_unweighted = cart_total_weight(list(cart.items.all()))
        self.assertEqual(total, Decimal('1.250'))
        self.assertFalse(has_unweighted)


class BilledKgTests(TestCase):
    def test_rounds_up_to_next_kg_with_one_kg_minimum(self):
        self.assertEqual(billed_kg(Decimal('0')), 0)
        self.assertEqual(billed_kg(Decimal('0.05')), 1)
        self.assertEqual(billed_kg(Decimal('1')), 1)
        self.assertEqual(billed_kg(Decimal('1.01')), 2)
        self.assertEqual(billed_kg(Decimal('2')), 2)


class DeliveryWeightUpsellMessageTests(TestCase):
    def test_slack_message_when_room_before_next_kg(self):
        self.assertEqual(delivery_weight_upsell_message(Decimal('0.5')), 'Add up to 500g more - no extra delivery')
        self.assertEqual(delivery_weight_upsell_message(Decimal('1.5')), 'Add up to 500g more - no extra delivery')

    def test_no_message_at_exact_kg_boundary(self):
        self.assertEqual(delivery_weight_upsell_message(Decimal('1')), '')
        self.assertEqual(delivery_weight_upsell_message(Decimal('2')), '')

    def test_no_message_for_empty_cart(self):
        self.assertEqual(delivery_weight_upsell_message(Decimal('0')), '')
        self.assertEqual(delivery_weight_upsell_message(None), '')
