"""REST API contract: authentication, permissions, validation and status codes."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from orders.models import Order, OrderStatus
from orders.services import assign_delivery_boy, create_order_from_cart
from tests.conftest import (
    PASSWORD,
    fill_cart,
    make_address,
    make_admin,
    make_category,
    make_coupon,
    make_customer,
    make_food,
    make_owner,
    make_rider,
)


class APITestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = make_customer("api.customer@test.foodies")
        cls.owner = make_owner("api.owner@test.foodies")
        cls.rider = make_rider("api.rider@test.foodies")
        cls.admin = make_admin("api.admin@test.foodies")
        cls.restaurant = cls.owner.restaurants.first()
        cls.category = make_category("API Category")
        cls.food = make_food(cls.restaurant, cls.category, name="API Paneer", price="260.00", discount_price="220.00")
        cls.coupon = make_coupon("API15", minimum="150.00", value="15")
        cls.address = make_address(cls.customer)
        fill_cart(cls.customer, (cls.food, 2))
        cls.order = create_order_from_cart(cls.customer, cls.address)
        assign_delivery_boy(cls.order, cls.rider, actor=cls.admin)

    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client


class PublicEndpointTests(APITestBase):
    def test_restaurant_and_menu_endpoints(self):
        client = self.api()
        listing = client.get("/api/restaurants/")
        self.assertEqual(listing.status_code, 200)
        slugs = [row["slug"] for row in listing.json()["results"]]
        self.assertIn(self.restaurant.slug, slugs)

        detail = client.get(f"/api/restaurants/{self.restaurant.slug}/")
        self.assertEqual(detail.status_code, 200)

        menu = client.get(f"/api/restaurants/{self.restaurant.slug}/menu/")
        self.assertEqual(menu.status_code, 200)

    def test_categories_and_food_search(self):
        client = self.api()
        categories = client.get("/api/categories/")
        self.assertEqual(categories.status_code, 200)

        results = client.get("/api/food/", {"search": "Paneer", "max_price": "1000"})
        self.assertEqual(results.status_code, 200)
        names = [row["name"] for row in results.json()["results"]]
        self.assertIn("API Paneer", names)

    def test_unapproved_restaurants_are_hidden(self):
        pending_owner = make_owner("api.pending@test.foodies", approved=False)
        pending = pending_owner.restaurants.first()
        client = self.api()
        slugs = [row["slug"] for row in client.get("/api/restaurants/").json()["results"]]
        self.assertNotIn(pending.slug, slugs)
        self.assertEqual(client.get(f"/api/restaurants/{pending.slug}/").status_code, 404)

    def test_offers_and_payment_config(self):
        client = self.api()
        offers = client.get("/api/offers/")
        self.assertEqual(offers.status_code, 200)
        config = client.get("/api/payments/config/")
        self.assertEqual(config.status_code, 200)
        self.assertIn("gateway", config.json())
        self.assertIn("currency", config.json())


class AuthEndpointTests(APITestBase):
    def test_register_login_me_logout(self):
        client = self.api()
        register = client.post(
            "/api/auth/register/",
            {
                "email": "api.newbie@test.foodies",
                "first_name": "New",
                "last_name": "Bie",
                "phone": "9811100011",
                "password": "Str0ngPass#2024",
                "password_confirm": "Str0ngPass#2024",
                "role": "CUSTOMER",
            },
            format="json",
        )
        self.assertIn(register.status_code, {200, 201})

        login = client.post(
            "/api/auth/login/", {"email": "api.newbie@test.foodies", "password": "Str0ngPass#2024"}, format="json"
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("token", login.json())

        token = login.json()["token"]
        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        me = client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "api.newbie@test.foodies")

        self.assertEqual(client.post("/api/auth/logout/").status_code, 200)
        self.assertIn(client.get("/api/auth/me/").status_code, {401, 403})

    def test_weak_registration_is_rejected(self):
        client = self.api()
        response = client.post(
            "/api/auth/register/",
            {"email": "bad@test.foodies", "password": "123", "password_confirm": "123", "role": "CUSTOMER"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_anonymous_cannot_read_private_endpoints(self):
        client = self.api()
        for url in ("/api/cart/", "/api/orders/", "/api/notifications/", "/api/addresses/", "/api/delivery/assignments/"):
            with self.subTest(url=url):
                self.assertIn(client.get(url).status_code, {401, 403})


class CartAndOrderAPITests(APITestBase):
    def test_cart_requires_a_customer(self):
        self.assertIn(self.api(self.owner).get("/api/cart/").status_code, {403, 404})

    def test_cart_lifecycle(self):
        client = self.api(self.customer)
        client.post("/api/cart/clear/")
        add = client.post("/api/cart/add/", {"food_item_id": self.food.pk, "quantity": 1}, format="json")
        self.assertIn(add.status_code, {200, 201})
        detail = client.get("/api/cart/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["items"])

    def test_add_missing_item_returns_404(self):
        client = self.api(self.customer)
        self.assertEqual(client.post("/api/cart/add/", {"food_item_id": 999999, "quantity": 1}, format="json").status_code, 404)

    def test_coupon_validation_endpoint(self):
        client = self.api(self.customer)
        client.post("/api/cart/clear/")
        client.post("/api/cart/add/", {"food_item_id": self.food.pk, "quantity": 2}, format="json")
        valid = client.post("/api/cart/coupon/", {"code": "API15"}, format="json")
        self.assertEqual(valid.status_code, 200)
        self.assertTrue(valid.json()["pricing"]["coupon_applied"])
        self.assertEqual(valid.json()["pricing"]["coupon_discount"], 66.0)  # 15% of 440

        invalid = client.post("/api/cart/coupon/", {"code": "NOPE"}, format="json")
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(invalid.json()["pricing"]["coupon_applied"])

    def test_place_order_endpoint(self):
        client = self.api(self.customer)
        client.post("/api/cart/clear/")
        client.post("/api/cart/add/", {"food_item_id": self.food.pk, "quantity": 1}, format="json")
        before = Order.objects.filter(customer=self.customer).count()
        response = client.post(
            "/api/orders/checkout/",
            {"address_id": self.address.pk, "payment_method": "COD"},
            format="json",
        )
        self.assertIn(response.status_code, {200, 201})
        self.assertEqual(Order.objects.filter(customer=self.customer).count(), before + 1)
        order = Order.objects.filter(customer=self.customer).latest("id")
        self.assertEqual(order.order_status, OrderStatus.PLACED)
        self.assertEqual(order.total_amount, order.subtotal + order.delivery_fee + order.tax + order.platform_fee - order.coupon_discount)

    def test_place_order_without_address_is_a_validation_error(self):
        client = self.api(self.customer)
        client.post("/api/cart/clear/")
        client.post("/api/cart/add/", {"food_item_id": self.food.pk, "quantity": 1}, format="json")
        response = client.post("/api/orders/checkout/", {"payment_method": "COD"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_another_customers_order_is_404(self):
        intruder = make_customer("api.intruder@test.foodies")
        response = self.api(intruder).get(f"/api/orders/{self.order.order_number}/")
        self.assertEqual(response.status_code, 404)

    def test_customer_cannot_list_delivery_assignments(self):
        self.assertEqual(self.api(self.customer).get("/api/delivery/assignments/").status_code, 403)

    def test_rider_only_sees_own_assignments(self):
        rider_api = self.api(self.rider)
        rows = rider_api.get("/api/delivery/assignments/").json()["results"]
        self.assertTrue(rows)
        self.assertTrue(all(row["order_number"] == self.order.order_number for row in rows))

        other_rider = make_rider("api.rider2@test.foodies")
        self.assertEqual(self.api(other_rider).get("/api/delivery/assignments/").json()["results"], [])

    def test_review_endpoint_requires_a_delivered_order(self):
        client = self.api(self.customer)
        response = client.post(
            f"/api/reviews/order/{self.order.order_number}/",
            {"rating": 5, "comment": "Not delivered yet"},
            format="json",
        )
        self.assertIn(response.status_code, {400, 403, 404})
