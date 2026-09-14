"""Admin + restaurant-owner dashboard actions (the buttons a human clicks)."""

from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from delivery.models import DeliveryBoyProfile
from menu.models import Category, FoodItem
from offers.models import Coupon
from orders.models import Notification, Order, OrderStatus
from orders.services import create_order_from_cart
from restaurants.models import Restaurant
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


class DashboardBase(TestCase):
    def login(self, email):
        client = Client()
        self.assertTrue(client.login(username=email, password=PASSWORD), f"login failed for {email}")
        return client


class AdminApprovalTests(DashboardBase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_admin("dash.admin@test.foodies")
        cls.pending_owner = make_owner("dash.pending@test.foodies", approved=False)
        cls.pending_restaurant = cls.pending_owner.restaurants.first()
        cls.rider = make_rider("dash.pending.rider@test.foodies", approved=False)
        cls.customer = make_customer("dash.customer@test.foodies")

    def test_pending_restaurant_is_invisible_until_approved(self):
        client = Client()
        self.assertEqual(client.get(f"/restaurants/{self.pending_restaurant.slug}/").status_code, 404)
        listed = client.get("/restaurants/").content.decode()
        self.assertNotIn(self.pending_restaurant.name, listed)

        admin = self.login(self.admin.email)
        self.assertIn(self.pending_restaurant.name, admin.get("/admin-dashboard/approvals/").content.decode())
        admin.post(reverse("dashboard:admin_approve_restaurant", args=[self.pending_restaurant.pk]), {"next": "/admin-dashboard/approvals/"})
        self.pending_restaurant.refresh_from_db()
        self.assertTrue(self.pending_restaurant.is_approved)
        self.assertEqual(Client().get(f"/restaurants/{self.pending_restaurant.slug}/").status_code, 200)

    def test_reject_records_a_reason_and_hides_the_restaurant(self):
        admin = self.login(self.admin.email)
        admin.post(
            reverse("dashboard:admin_reject_restaurant", args=[self.pending_restaurant.pk]),
            {"reason": "FSSAI licence missing", "next": "/admin-dashboard/approvals/"},
        )
        self.pending_restaurant.refresh_from_db()
        self.assertFalse(self.pending_restaurant.is_approved)
        self.assertIn("FSSAI", self.pending_restaurant.rejection_reason)
        self.assertEqual(Client().get(f"/restaurants/{self.pending_restaurant.slug}/").status_code, 404)

    def test_admin_can_block_and_unblock_an_account(self):
        admin = self.login(self.admin.email)
        admin.post(reverse("dashboard:admin_toggle_user", args=[self.customer.pk]), {"next": "/admin-dashboard/customers/"})
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

        blocked_client = Client()
        self.assertFalse(blocked_client.login(username=self.customer.email, password=PASSWORD))

        admin.post(reverse("dashboard:admin_toggle_user", args=[self.customer.pk]), {"next": "/admin-dashboard/customers/"})
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    def test_admin_approves_a_delivery_partner(self):
        admin = self.login(self.admin.email)
        profile = self.rider.delivery_profile
        self.assertFalse(profile.is_approved)
        admin.post(reverse("dashboard:admin_toggle_delivery", args=[self.rider.pk]), {"next": "/admin-dashboard/delivery-boys/"})
        profile.refresh_from_db()
        self.assertTrue(profile.is_approved)

    def test_admin_creates_and_toggles_a_category(self):
        admin = self.login(self.admin.email)
        response = admin.post(
            reverse("dashboard:admin_category_create"),
            {"name": "Dashboard Desserts", "slug": "dashboard-desserts", "icon": "🍰", "display_order": 3, "is_active": "on"},
        )
        self.assertIn(response.status_code, {200, 302})
        category = Category.objects.filter(slug="dashboard-desserts").first()
        self.assertIsNotNone(category)
        self.assertTrue(category.is_active)

        admin.post(reverse("dashboard:admin_category_delete", args=[category.pk]))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())

    def test_admin_creates_a_coupon_and_toggles_it(self):
        admin = self.login(self.admin.email)
        response = admin.post(
            reverse("dashboard:admin_coupon_create"),
            {
                "code": "DASH50",
                "title": "Dashboard coupon",
                "discount_type": "PERCENT",
                "discount_value": "50",
                "minimum_order": "300",
                "maximum_discount": "100",
                "valid_from": "2024-01-01T00:00",
                "valid_until": "2030-01-01T00:00",
                "usage_limit": "50",
                "per_user_limit": "1",
                "is_active": "on",
            },
        )
        self.assertIn(response.status_code, {200, 302})
        coupon = Coupon.objects.filter(code="DASH50").first()
        self.assertIsNotNone(coupon, "coupon form should create a coupon")

        admin.post(reverse("dashboard:admin_toggle_coupon", args=[coupon.pk]), {"next": "/admin-dashboard/coupons/"})
        coupon.refresh_from_db()
        self.assertFalse(coupon.is_active)

    def test_admin_toggles_a_food_item_availability(self):
        owner = make_owner("dash.menu.owner@test.foodies")
        restaurant = owner.restaurants.first()
        food = make_food(restaurant, name="Toggle Dish")
        admin = self.login(self.admin.email)
        admin.post(reverse("dashboard:admin_toggle_food", args=[food.pk]), {"next": "/admin-dashboard/food/"})
        food.refresh_from_db()
        self.assertFalse(food.is_available)


class RestaurantOwnerActionTests(DashboardBase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_owner("dash.owner@test.foodies")
        cls.other_owner = make_owner("dash.owner2@test.foodies")
        cls.restaurant = cls.owner.restaurants.first()
        cls.customer = make_customer("dash.foodie@test.foodies")
        cls.address = make_address(cls.customer)
        cls.dish = make_food(cls.restaurant, name="Owner Dish", price="240.00")
        fill_cart(cls.customer, (cls.dish, 1))
        cls.order = create_order_from_cart(cls.customer, cls.address)

    def test_owner_accepts_prepares_and_completes_an_order(self):
        owner = self.login(self.owner.email)
        page = owner.get("/restaurant-dashboard/orders/").content.decode()
        self.assertIn(self.order.order_number, page)

        owner.post(reverse("dashboard:restaurant_order_action", args=[self.order.order_number, "accept"]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CONFIRMED)
        self.assertTrue(Notification.objects.filter(recipient=self.customer, order=self.order).exists())

        owner.post(reverse("dashboard:restaurant_order_action", args=[self.order.order_number, "preparing"]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.PREPARING)

        owner.post(reverse("dashboard:restaurant_order_action", args=[self.order.order_number, "ready"]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.READY_FOR_PICKUP)

    def test_owner_rejects_an_order_with_a_reason(self):
        owner = self.login(self.owner.email)
        owner.post(
            reverse("dashboard:restaurant_order_action", args=[self.order.order_number, "reject"]),
            {"reason": "Kitchen is out of paneer"},
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.CANCELLED)
        self.assertIn("paneer", self.order.cancellation_reason)

    def test_owner_cannot_skip_steps(self):
        owner = self.login(self.owner.email)
        owner.post(reverse("dashboard:restaurant_order_action", args=[self.order.order_number, "ready"]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.PLACED)

    def test_owner_creates_and_edits_a_menu_item(self):
        owner = self.login(self.owner.email)
        category = make_category("Owner Category")
        response = owner.post(
            reverse("dashboard:restaurant_food_create"),
            {
                "category": category.pk,
                "name": "Owner Special Thali",
                "description": "Chef's special",
                "price": "399.00",
                "discount_price": "349.00",
                "is_veg": "on",
                "is_available": "on",
                "preparation_time": 20,
            },
        )
        self.assertIn(response.status_code, {200, 302})
        food = FoodItem.objects.filter(restaurant=self.restaurant, name="Owner Special Thali").first()
        self.assertIsNotNone(food)
        self.assertEqual(food.restaurant, self.restaurant)
        self.assertEqual(food.final_price, Decimal("349.00"))

        owner.post(reverse("dashboard:restaurant_toggle_food", args=[food.pk]), {"next": "/restaurant-dashboard/menu/"})
        food.refresh_from_db()
        self.assertFalse(food.is_available)

    def test_owner_toggles_restaurant_open_state(self):
        owner = self.login(self.owner.email)
        owner.post(reverse("dashboard:restaurant_toggle_open"))
        self.restaurant.refresh_from_db()
        self.assertFalse(self.restaurant.is_open)

        # Closed restaurants cannot receive new orders.
        fill_cart(self.customer, (self.dish, 1))
        response = self.login(self.customer.email).post(
            "/checkout/", {"address_id": self.address.pk, "payment_method": "COD"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.filter(customer=self.customer).count(), 1)

    def test_owner_creates_a_restaurant_scoped_coupon(self):
        owner = self.login(self.owner.email)
        response = owner.post(
            reverse("dashboard:restaurant_offers"),
            {
                "code": "OWNER25",
                "title": "Owner offer",
                "discount_type": "PERCENT",
                "discount_value": "25",
                "minimum_order": "250",
                "maximum_discount": "120",
                "valid_from": "2024-01-01T00:00",
                "valid_until": "2030-01-01T00:00",
                "usage_limit": "25",
                "per_user_limit": "1",
                "is_active": "on",
            },
        )
        self.assertIn(response.status_code, {200, 302})
        coupon = Coupon.objects.filter(code="OWNER25").first()
        self.assertIsNotNone(coupon)
        self.assertEqual(coupon.restaurant, self.restaurant)

    def test_owner_can_update_profile_and_vehicle_free_fields(self):
        owner = self.login(self.owner.email)
        response = owner.post(
            reverse("dashboard:restaurant_profile"),
            {
                "name": "Renamed Kitchen",
                "description": "Updated",
                "phone": "9800000001",
                "email": "kitchen@test.foodies",
                "address": "1 Test Street",
                "area": "Test Area",
                "city": "Ahmedabad",
                "state": "Gujarat",
                "pincode": "380015",
                "cuisine_type": "Pizza, Italian",
                "delivery_time": 25,
                "delivery_fee": "19.00",
                "minimum_order": "149.00",
                "is_open": "on",
            },
        )
        self.assertIn(response.status_code, {200, 302})
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.name, "Renamed Kitchen")

    def test_owner_without_restaurant_is_pushed_to_create_one(self):
        owner = make_owner("dash.owner3@test.foodies", with_restaurant=False)
        client = self.login(owner.email)
        response = client.get("/restaurant-dashboard/orders/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("restaurant/create", response.url)
