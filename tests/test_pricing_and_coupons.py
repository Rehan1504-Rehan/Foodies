"""Money must always be calculated on the server, never trusted from a browser."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from cart.services import calculate_pricing, resolve_coupon
from menu.models import FoodItem
from offers.models import Coupon
from orders.models import Order, OrderStatus
from orders.services import create_order_from_cart
from tests.conftest import (
    fill_cart,
    make_address,
    make_coupon,
    make_customer,
    make_food,
    make_owner,
)


class PricingEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = make_customer("price.customer@test.foodies")
        cls.owner = make_owner("price.owner@test.foodies")
        cls.restaurant = cls.owner.restaurants.first()
        cls.restaurant.delivery_fee = Decimal("29.00")
        cls.restaurant.minimum_order = Decimal("99.00")
        cls.restaurant.save()
        cls.dish = make_food(cls.restaurant, name="Paneer Tikka", price="300.00", discount_price="240.00")
        cls.cart = fill_cart(cls.customer, (cls.dish, 2))

    def test_item_discount_and_totals(self):
        pricing = calculate_pricing(self.cart)
        self.assertEqual(pricing.mrp_total, Decimal("600.00"))
        self.assertEqual(pricing.subtotal, Decimal("480.00"))
        self.assertEqual(pricing.food_discount, Decimal("120.00"))
        self.assertEqual(pricing.tax, Decimal("24.00"))  # 5% of 480
        self.assertEqual(pricing.platform_fee, Decimal("5.00"))
        self.assertEqual(pricing.delivery_fee, Decimal("29.00"))  # below free threshold
        self.assertEqual(pricing.total, Decimal("538.00"))

    def test_free_delivery_above_threshold(self):
        big = make_food(self.restaurant, name="Family Platter", price="600.00")
        cart = fill_cart(self.customer, (big, 1))
        pricing = calculate_pricing(cart)
        self.assertEqual(pricing.delivery_fee, Decimal("0.00"))
        self.assertGreaterEqual(pricing.subtotal, Decimal("499.00"))

    def test_minimum_order_is_enforced(self):
        cheap = make_food(self.restaurant, name="Single Samosa", price="40.00")
        cart = fill_cart(self.customer, (cheap, 1))
        pricing = calculate_pricing(cart)
        self.assertTrue(pricing.issues)
        self.assertTrue(any("Minimum order" in issue for issue in pricing.issues))

    def test_unavailable_item_blocks_checkout(self):
        self.dish.is_available = False
        self.dish.save(update_fields=["is_available"])
        pricing = calculate_pricing(self.cart)
        self.assertTrue(any("unavailable" in issue.lower() for issue in pricing.issues))
        self.dish.is_available = True
        self.dish.save(update_fields=["is_available"])

    def test_closed_restaurant_blocks_checkout(self):
        self.restaurant.is_open = False
        self.restaurant.save(update_fields=["is_open"])
        pricing = calculate_pricing(self.cart)
        self.assertTrue(any("closed" in issue.lower() for issue in pricing.issues))
        self.restaurant.is_open = True
        self.restaurant.save(update_fields=["is_open"])

    def test_percentage_coupon_discount_and_cap(self):
        coupon = make_coupon("BIG50", minimum="100.00", value="50", maximum_discount=Decimal("100.00"))
        pricing = calculate_pricing(self.cart, coupon=coupon, user=self.customer)
        self.assertTrue(pricing.coupon_applied)
        self.assertEqual(pricing.coupon_discount, Decimal("100.00"))  # capped
        # 480 subtotal − 100 coupon + 29 delivery + 24 tax + 5 platform fee
        self.assertEqual(pricing.total, Decimal("438.00"))

    def test_fixed_coupon_discount(self):
        coupon = make_coupon("FLAT75", minimum="100.00", value="75", dtype="FIXED")
        pricing = calculate_pricing(self.cart, coupon=coupon, user=self.customer)
        self.assertEqual(pricing.coupon_discount, Decimal("75.00"))

    def test_coupon_below_minimum_is_rejected_with_message(self):
        coupon = make_coupon("NEED1000", minimum="1000.00", value="10")
        ok, message = resolve_coupon("NEED1000", self.customer, Decimal("480.00"), self.restaurant)
        self.assertIsNone(ok)
        self.assertIn("more to use", message)
        pricing = calculate_pricing(self.cart, coupon=coupon, user=self.customer)
        self.assertFalse(pricing.coupon_applied)
        self.assertTrue(pricing.issues)

    def test_expired_and_inactive_coupons_are_rejected(self):
        expired = make_coupon("OLD10", minimum="100.00", value="10")
        expired.valid_until = timezone.now() - timedelta(days=1)
        expired.save(update_fields=["valid_until"])
        ok, _ = resolve_coupon("OLD10", self.customer, Decimal("480.00"), self.restaurant)
        self.assertIsNone(ok)

        paused = make_coupon("PAUSED10", minimum="100.00", value="10", is_active=False)
        self.assertIsNotNone(paused)
        ok, _ = resolve_coupon("PAUSED10", self.customer, Decimal("480.00"), self.restaurant)
        self.assertIsNone(ok)

    def test_coupon_of_another_restaurant_is_rejected(self):
        other_owner = make_owner("rival.owner@test.foodies")
        coupon = make_coupon("RIVAL30", minimum="100.00", value="30", restaurant=other_owner.restaurants.first())
        ok, _ = resolve_coupon("RIVAL30", self.customer, Decimal("480.00"), self.restaurant)
        self.assertIsNone(ok)

    def test_first_order_only_coupon(self):
        coupon = make_coupon("FIRSTONLY", minimum="100.00", value="30", first_order_only=True)
        ok, _ = resolve_coupon("FIRSTONLY", self.customer, Decimal("480.00"), self.restaurant)
        self.assertIsNotNone(ok)
        address = make_address(self.customer)
        create_order_from_cart(self.customer, address, coupon_code="FIRSTONLY")
        fill_cart(self.customer, (self.dish, 2))
        ok, message = resolve_coupon("FIRSTONLY", self.customer, Decimal("480.00"), self.restaurant)
        self.assertIsNone(ok)
        self.assertTrue(message)


class OrderSnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = make_customer("snap.customer@test.foodies")
        cls.owner = make_owner("snap.owner@test.foodies")
        cls.restaurant = cls.owner.restaurants.first()
        cls.dish = make_food(cls.restaurant, name="Butter Naan", price="60.00", discount_price="50.00")
        cls.address = make_address(cls.customer)

    def test_order_stores_item_name_and_price_snapshot(self):
        fill_cart(self.customer, (self.dish, 3))
        order = create_order_from_cart(self.customer, self.address)
        item = order.items.get()
        self.assertEqual(item.food_name, "Butter Naan")
        self.assertEqual(item.price, Decimal("50.00"))
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.total, Decimal("150.00"))

        # Changing the menu afterwards must not rewrite order history.
        self.dish.name = "Renamed Naan"
        self.dish.discount_price = Decimal("10.00")
        self.dish.save()
        item.refresh_from_db()
        self.assertEqual(item.food_name, "Butter Naan")
        self.assertEqual(item.price, Decimal("50.00"))

    def test_order_number_and_status_defaults(self):
        fill_cart(self.customer, (self.dish, 2))
        order = create_order_from_cart(self.customer, self.address)
        self.assertTrue(order.order_number.startswith("FD"))
        self.assertEqual(order.order_status, OrderStatus.PLACED)
        self.assertEqual(order.customer_name, self.address.full_name)
        self.assertIn(self.address.area, order.delivery_address_text)

    def test_cart_is_cleared_and_payment_recorded(self):
        fill_cart(self.customer, (self.dish, 2))
        order = create_order_from_cart(self.customer, self.address, payment_method="COD")
        self.assertEqual(self.customer.cart.cart_items.count(), 0)
        payment = order.payments.first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.amount, order.total_amount)

    def test_checkout_rejects_empty_cart_and_foreign_address(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            create_order_from_cart(self.customer, self.address)

        fill_cart(self.customer, (self.dish, 2))
        other = make_customer("foreign.address@test.foodies")
        with self.assertRaises(ValidationError):
            create_order_from_cart(self.customer, make_address(other))

    def test_price_tampering_in_request_is_ignored(self):
        """A forged price in POST data must not reach the database."""
        payload = {"food_item_id": self.dish.pk, "quantity": 2, "price": "1.00"}
        self.client.force_login(self.customer)
        self.client.post("/api/cart/add/", payload)
        order = create_order_from_cart(self.customer, self.address)
        self.assertEqual(order.items.get().price, Decimal("50.00"))
        self.assertNotEqual(order.total_amount, Decimal("2.00"))
