"""The FOODIES acceptance journey, exactly as a human would drive it.

customer signup → address → browse → cart → coupon → checkout → owner accepts
and cooks → admin assigns a partner → partner delivers → customer reviews.
"""

from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Address, User
from cart.models import Cart
from delivery.models import DeliveryAssignment, DeliveryEarning
from menu.models import FoodItem
from offers.models import Coupon
from orders.models import Notification, Order, OrderItem, OrderStatus
from payments.models import Payment
from restaurants.models import Restaurant
from reviews.models import Review
from tests.conftest import PASSWORD, make_admin, make_coupon, make_food, make_owner, make_rider

CUSTOMER_EMAIL = "journey.customer@test.foodies"
CUSTOMER_PASSWORD = "Sunshine#2024"


class FullJourneyTests(TestCase):
    """One continuous order, driven through all four interfaces."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_owner("journey.owner@test.foodies")
        cls.rider = make_rider("journey.rider@test.foodies")
        cls.admin = make_admin("journey.admin@test.foodies")
        cls.restaurant: Restaurant = cls.owner.restaurants.first()
        cls.restaurant.is_open = True
        cls.restaurant.save(update_fields=["is_open"])
        cls.dish_one = make_food(cls.restaurant, name="Journey Biryani", price="379.00", discount_price="329.00")
        cls.dish_two = make_food(cls.restaurant, name="Journey Naan", price="179.00")
        cls.coupon = make_coupon("JOURNEY20", minimum="199.00", value="20", maximum_discount=Decimal("150.00"))

    # ------------------------------------------------------------- helpers
    def register_customer(self):
        response = self.client.post(
            "/accounts/register/customer/",
            {
                "first_name": "Journey",
                "last_name": "Tester",
                "email": CUSTOMER_EMAIL,
                "phone": "9812345678",
                "password1": CUSTOMER_PASSWORD,
                "password2": CUSTOMER_PASSWORD,
            },
        )
        self.assertIn(response.status_code, {200, 302})
        user = User.objects.get(email=CUSTOMER_EMAIL)
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(user.password.startswith("pbkdf2_"), "password must be hashed")
        self.assertTrue(self.client.login(username=CUSTOMER_EMAIL, password=CUSTOMER_PASSWORD))
        return user

    # --------------------------------------------------------------- tests
    def test_full_four_role_journey(self):
        # 1 ── customer registration -------------------------------------
        customer = self.register_customer()

        # 2 ── address book ----------------------------------------------
        self.client.post(
            "/accounts/addresses/new/",
            {
                "full_name": "Journey Tester",
                "phone": "9812345678",
                "address_line": "12 Sunrise Apartments",
                "area": "Satellite",
                "city": "Ahmedabad",
                "state": "Gujarat",
                "pincode": "380015",
                "landmark": "Near Cross Road",
                "address_type": "HOME",
                "is_default": "on",
            },
        )
        address = Address.objects.get(user=customer)
        self.assertTrue(address.is_default)

        # 3 ── browse and add to cart -------------------------------------
        self.assertEqual(self.client.get(reverse("restaurants:detail", args=[self.restaurant.slug])).status_code, 200)
        self.assertEqual(self.client.get("/search/", {"q": "Journey"}).status_code, 200)
        self.assertIn(self.client.post("/api/cart/add/", {"food_item_id": self.dish_one.pk, "quantity": 2}).status_code, {200, 201})
        self.assertIn(self.client.post("/api/cart/add/", {"food_item_id": self.dish_two.pk, "quantity": 1}).status_code, {200, 201})
        self.assertEqual(Cart.objects.get(user=customer).cart_items.count(), 2)

        # 4 ── coupon + server side bill ----------------------------------
        self.assertIn(self.client.post("/cart/coupon/apply/", {"code": "JOURNEY20"}).status_code, {200, 302})
        self.assertEqual(self.client.session.get("coupon_id"), self.coupon.pk)
        self.assertEqual(self.client.get("/checkout/").status_code, 200)

        # 5 ── place the order (COD) --------------------------------------
        response = self.client.post(
            "/checkout/",
            {"address_id": address.pk, "payment_method": "COD", "special_instructions": "Ring the bell twice"},
        )
        self.assertIn(response.status_code, {200, 302})
        order = Order.objects.filter(customer=customer).latest("id")
        self.assertEqual(order.order_status, OrderStatus.PLACED)
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.delivery_address_text, address.full_address)
        self.assertEqual(order.customer_phone, address.phone)
        self.assertEqual(order.coupon, self.coupon)
        self.assertGreater(order.coupon_discount, Decimal("0.00"))

        expected_total = (
            order.subtotal + order.delivery_fee + order.tax + order.platform_fee - order.coupon_discount
        )
        self.assertEqual(order.total_amount, expected_total)

        # Food name and price are frozen at order time.
        biryani = OrderItem.objects.get(order=order, food_item=self.dish_one)
        self.assertEqual(biryani.food_name, "Journey Biryani")
        self.assertEqual(biryani.price, Decimal("329.00"))
        self.assertEqual(biryani.mrp, Decimal("379.00"))
        self.assertEqual(Cart.objects.get(user=customer).cart_items.count(), 0)
        self.assertTrue(Payment.objects.filter(order=order).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.owner, order=order).exists())

        # 6 ── restaurant owner accepts and cooks -------------------------
        owner_client = Client()
        self.assertTrue(owner_client.login(username=self.owner.email, password=PASSWORD))
        self.assertIn(order.order_number, owner_client.get("/restaurant-dashboard/orders/").content.decode())
        for action, expected in [
            ("accept", OrderStatus.CONFIRMED),
            ("preparing", OrderStatus.PREPARING),
            ("ready", OrderStatus.READY_FOR_PICKUP),
        ]:
            owner_client.post(
                reverse("dashboard:restaurant_order_action", args=[order.order_number, action])
            )
            order.refresh_from_db()
            self.assertEqual(order.order_status, expected, action)

        # 7 ── admin assigns a delivery partner ---------------------------
        admin_client = Client()
        self.assertTrue(admin_client.login(username=self.admin.email, password=PASSWORD))
        self.assertIn(order.order_number, admin_client.get("/admin-dashboard/delivery/").content.decode())
        admin_client.post(
            reverse("dashboard:admin_assign_partner", args=[order.order_number]),
            {"delivery_boy": self.rider.pk, "next": "/admin-dashboard/delivery/"},
        )
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.ASSIGNED)
        self.assertEqual(order.delivery_boy, self.rider)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.rider, order=order, title__icontains="assigned"
            ).exists()
        )

        # 8 ── partner delivers -------------------------------------------
        rider_client = Client()
        self.assertTrue(rider_client.login(username=self.rider.email, password=PASSWORD))
        self.assertIn(order.order_number, rider_client.get("/delivery/").content.decode())
        self.assertEqual(rider_client.get(f"/delivery/orders/{order.order_number}/").status_code, 200)
        # The partner accepts the job, then walks the delivery pipeline.
        for step in ("ACCEPTED", "PICKED_UP", "OUT_FOR_DELIVERY", "DELIVERED"):
            rider_client.post(reverse("delivery:update_status", args=[order.order_number, step]))
            order.refresh_from_db()
            expected = "ASSIGNED" if step == "ACCEPTED" else step
            self.assertEqual(order.order_status, expected, step)
            order.assignment.refresh_from_db()
            self.assertEqual(order.assignment.status, step, step)

        assignment = DeliveryAssignment.objects.get(order=order)
        self.assertEqual(assignment.status, DeliveryAssignment.Status.DELIVERED)
        self.assertIsNotNone(order.delivered_at)
        earning = DeliveryEarning.objects.get(order=order, delivery_boy=self.rider)
        self.assertGreater(earning.amount, Decimal("0.00"))

        # 9 ── customer sees DELIVERED, tracks and reviews ----------------
        customer_client = Client()
        self.assertTrue(customer_client.login(username=CUSTOMER_EMAIL, password=CUSTOMER_PASSWORD))
        self.assertIn(order.order_number, customer_client.get("/orders/").content.decode())
        self.assertEqual(customer_client.get(f"/orders/{order.order_number}/").status_code, 200)
        self.assertEqual(customer_client.get(f"/orders/{order.order_number}/track/").status_code, 200)
        self.assertEqual(customer_client.get(f"/orders/{order.order_number}/invoice/").status_code, 200)

        payload = customer_client.get(f"/api/orders/{order.order_number}/track/").json()
        self.assertEqual(payload["status"], OrderStatus.DELIVERED)
        self.assertTrue(payload["steps"])

        customer_client.post(
            reverse("reviews:create", args=[order.order_number]),
            {"rating": 5, "comment": "Hot, fresh and delivered early. Great job FOODIES!"},
        )
        review = Review.objects.get(order=order)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.restaurant, self.restaurant)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.rating_count, 1)

        # 10 ── dashboards reflect reality --------------------------------
        self.assertTrue(Notification.objects.filter(recipient=self.admin, order=order).exists())
        rider_earnings = rider_client.get("/delivery/earnings/").content.decode()
        self.assertIn(order.order_number, rider_client.get("/delivery/history/").content.decode())
        self.assertEqual(rider_client.get("/delivery/earnings/").status_code, 200)
        self.assertIsNotNone(rider_earnings)

    def test_checkout_is_atomic_when_an_item_goes_out_of_stock(self):
        customer = self.register_customer()
        address = Address.objects.create(
            user=customer,
            full_name="Journey Tester",
            phone="9812345678",
            address_line="12 Sunrise Apartments",
            area="Satellite",
            city="Ahmedabad",
            state="Gujarat",
            pincode="380015",
            address_type=Address.AddressType.HOME,
            is_default=True,
        )
        self.client.post("/api/cart/add/", {"food_item_id": self.dish_one.pk, "quantity": 1})
        self.dish_two.is_available = True

        # The restaurant closes while the cart sits in the browser.
        self.restaurant.is_open = False
        self.restaurant.save(update_fields=["is_open"])
        response = self.client.post("/checkout/", {"address_id": address.pk, "payment_method": "COD"})
        # The view bounces back to the cart with an explanatory message …
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("cart:detail"))
        # … and the transaction rolled back completely: no half-built order.
        self.assertFalse(Order.objects.filter(customer=customer).exists())
        self.assertFalse(OrderItem.objects.filter(order__customer=customer).exists())
        self.assertFalse(Payment.objects.filter(order__customer=customer).exists())
        # Cart survives so the customer can try again.
        self.assertEqual(Cart.objects.get(user=customer).cart_items.count(), 1)

        self.restaurant.is_open = True
        self.restaurant.save(update_fields=["is_open"])
        self.assertEqual(self.client.post("/checkout/", {"address_id": address.pk, "payment_method": "COD"}).status_code, 302)
        self.assertEqual(Order.objects.filter(customer=customer).count(), 1)

    def test_payment_methods_record_the_right_status(self):
        customer = self.register_customer()
        address = Address.objects.create(
            user=customer,
            full_name="Journey Tester",
            phone="9812345678",
            address_line="12 Sunrise Apartments",
            area="Satellite",
            city="Ahmedabad",
            state="Gujarat",
            pincode="380015",
            address_type=Address.AddressType.HOME,
            is_default=True,
        )
        self.client.post("/api/cart/add/", {"food_item_id": self.dish_one.pk, "quantity": 1})
        self.client.post("/checkout/", {"address_id": address.pk, "payment_method": "COD"})
        order = Order.objects.filter(customer=customer).latest("id")
        self.assertEqual(order.payment_status, "COD")
        self.assertEqual(order.payments.first().payment_method, "COD")
