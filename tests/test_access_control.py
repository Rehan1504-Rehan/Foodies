"""Role based access control: every role must stay inside its own area.

Covers the customer / restaurant owner / delivery partner / admin matrix and
the object-level rules (nobody may read or mutate another party's records).
"""

from django.test import TestCase
from django.urls import reverse

from orders.models import Notification, Order, OrderStatus
from orders.services import assign_delivery_boy, create_order_from_cart
from tests.conftest import (
    fill_cart,
    make_address,
    make_admin,
    make_category,
    make_customer,
    make_food,
    make_owner,
    make_rider,
)

LOGIN_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
BLOCKED_STATUSES = {301, 302, 303, 307, 308, 403, 404}


class AccessControlBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = make_customer("customer@test.foodies")
        cls.other_customer = make_customer("other.customer@test.foodies")
        cls.owner = make_owner("owner@test.foodies")
        cls.other_owner = make_owner("other.owner@test.foodies")
        cls.rider = make_rider("rider@test.foodies")
        cls.other_rider = make_rider("other.rider@test.foodies")
        cls.admin = make_admin("admin@test.foodies")

        cls.restaurant = cls.owner.restaurants.first()
        cls.other_restaurant = cls.other_owner.restaurants.first()
        cls.category = make_category("Access Category")
        cls.food = make_food(cls.restaurant, cls.category, name="Access Dish", price="250.00")
        cls.other_food = make_food(cls.other_restaurant, cls.category, name="Rival Dish", price="260.00")
        cls.address = make_address(cls.customer)
        cls.other_address = make_address(cls.other_customer)

    def login_as(self, user):
        self.client.force_login(user)
        return self.client

    def assertBlocked(self, response, label="area"):
        self.assertIn(
            response.status_code,
            BLOCKED_STATUSES,
            f"{label} should be blocked but returned {response.status_code}",
        )


class CrossRoleDashboardTests(AccessControlBase):
    """Each role is locked out of the three dashboards it does not own."""

    CUSTOMER_FORBIDDEN = [
        "/admin-dashboard/",
        "/admin-dashboard/customers/",
        "/admin-dashboard/payments/",
        "/admin-dashboard/reports/",
        "/admin-dashboard/settings/",
        "/restaurant-dashboard/",
        "/restaurant-dashboard/orders/",
        "/restaurant-dashboard/sales/",
        "/delivery/",
        "/delivery/earnings/",
        "/delivery/available/",
    ]
    OWNER_FORBIDDEN = [
        "/admin-dashboard/",
        "/admin-dashboard/customers/",
        "/admin-dashboard/coupons/",
        "/delivery/",
        "/delivery/history/",
    ]
    RIDER_FORBIDDEN = [
        "/admin-dashboard/",
        "/admin-dashboard/delivery-boys/",
        "/restaurant-dashboard/",
        "/restaurant-dashboard/menu/",
    ]

    def test_customer_blocked_from_staff_areas(self):
        self.login_as(self.customer)
        for url in self.CUSTOMER_FORBIDDEN:
            with self.subTest(url=url):
                self.assertBlocked(self.client.get(url), url)

    def test_owner_blocked_from_admin_and_delivery(self):
        self.login_as(self.owner)
        for url in self.OWNER_FORBIDDEN:
            with self.subTest(url=url):
                self.assertBlocked(self.client.get(url), url)

    def test_rider_blocked_from_admin_and_restaurant(self):
        self.login_as(self.rider)
        for url in self.RIDER_FORBIDDEN:
            with self.subTest(url=url):
                self.assertBlocked(self.client.get(url), url)

    def test_django_admin_is_superuser_only(self):
        for user in (self.customer, self.owner, self.rider):
            self.login_as(user)
            with self.subTest(role=user.role):
                response = self.client.get("/django-admin/")
                self.assertNotEqual(response.status_code, 200)

    def test_anonymous_users_are_sent_to_login(self):
        for url in ("/admin-dashboard/", "/restaurant-dashboard/", "/delivery/", "/orders/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(response.status_code, LOGIN_REDIRECT_STATUSES)


class ObjectLevelSecurityTests(AccessControlBase):
    """Nobody may read or change records that belong to somebody else."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        fill_cart(cls.customer, (cls.food, 2))
        fill_cart(cls.other_customer, (cls.other_food, 2))
        cls.order = create_order_from_cart(
            user=cls.customer, address=cls.address, payment_method="COD"
        )
        cls.other_order = create_order_from_cart(
            user=cls.other_customer, address=cls.other_address, payment_method="COD"
        )
        assign_delivery_boy(cls.other_order, cls.other_rider, actor=cls.admin)

    def test_customer_cannot_open_another_customers_order(self):
        self.login_as(self.customer)
        response = self.client.get(reverse("orders:detail", args=[self.other_order.order_number]))
        self.assertBlocked(response, "other customer's order")
        self.assertBlocked(
            self.client.get(reverse("orders:track", args=[self.other_order.order_number])),
            "other customer's tracking page",
        )

    def test_customer_can_open_own_order(self):
        self.login_as(self.customer)
        response = self.client.get(reverse("orders:detail", args=[self.order.order_number]))
        self.assertEqual(response.status_code, 200)

    def test_rider_cannot_open_another_riders_delivery(self):
        self.login_as(self.rider)
        response = self.client.get(reverse("delivery:order_detail", args=[self.other_order.order_number]))
        self.assertBlocked(response, "another rider's delivery")

    def test_rider_cannot_change_another_riders_delivery(self):
        self.login_as(self.rider)
        response = self.client.post(
            reverse("delivery:update_status", args=[self.other_order.order_number, "PICKED_UP"])
        )
        self.assertBlocked(response, "status change on another rider's delivery")
        self.other_order.refresh_from_db()
        self.assertEqual(self.other_order.order_status, OrderStatus.ASSIGNED)
        self.assertIsNone(self.other_order.assignment.delivered_at)

    def test_owner_cannot_see_another_restaurants_order(self):
        self.login_as(self.owner)
        response = self.client.get(
            reverse("dashboard:restaurant_order_detail", args=[self.other_order.order_number])
        )
        self.assertBlocked(response, "another restaurant's order")

    def test_owner_cannot_act_on_another_restaurants_order(self):
        self.login_as(self.owner)
        self.other_order.refresh_from_db()
        status_before = self.other_order.order_status
        response = self.client.post(
            reverse("dashboard:restaurant_order_action", args=[self.other_order.order_number, "accept"])
        )
        self.assertBlocked(response, "accepting another restaurant's order")
        self.other_order.refresh_from_db()
        self.assertEqual(self.other_order.order_status, status_before)

    def test_owner_cannot_edit_another_restaurants_food(self):
        self.login_as(self.owner)
        foreign_food = self.other_food
        response = self.client.post(
            reverse("dashboard:restaurant_food_edit", args=[foreign_food.pk]),
            {"name": "Hacked Dish", "price": "1.00"},
        )
        self.assertBlocked(response, "editing another restaurant's menu item")
        foreign_food.refresh_from_db()
        self.assertNotEqual(foreign_food.name, "Hacked Dish")

    def test_customer_cannot_read_admin_api(self):
        self.login_as(self.customer)
        response = self.client.get("/api/delivery/assignments/")
        self.assertIn(response.status_code, {403, 404})
