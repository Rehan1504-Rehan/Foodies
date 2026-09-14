"""Every page of every interface must render with real data (no 500s)."""

from django.test import Client, TestCase

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


class PageSmokeTests(TestCase):
    """Renders each role's whole interface against seeded-in-test data."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = make_customer("pages.customer@test.foodies")
        cls.owner = make_owner("pages.owner@test.foodies")
        cls.admin = make_admin("pages.admin@test.foodies")
        cls.rider = make_rider("pages.rider@test.foodies")
        cls.restaurant = cls.owner.restaurants.first()
        cls.category = make_category("Page Category")
        cls.food = make_food(cls.restaurant, cls.category, name="Page Dish", price="180.00")
        cls.coupon = make_coupon("PAGES10", minimum="100.00", value="10")
        cls.address = make_address(cls.customer)
        fill_cart(cls.customer, (cls.food, 1))
        cls.order = create_order_from_cart(cls.customer, cls.address)
        assign_delivery_boy(cls.order, cls.rider, actor=cls.admin)
        cls.order.refresh_from_db()

    def assertRenders(self, client, urls):
        for url in urls:
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, 200, f"{url} -> {response.status_code}")

    def test_public_pages(self):
        self.assertRenders(
            Client(),
            [
                "/",
                "/search/?q=dish",
                "/restaurants/",
                f"/restaurants/{self.restaurant.slug}/",
                "/categories/",
                f"/categories/{self.category.slug}/",
                "/offers/",
                "/about/",
                "/contact/",
                "/healthz/",
                "/accounts/login/",
                "/accounts/register/customer/",
                "/accounts/register/restaurant/",
                "/accounts/register/delivery/",
                "/api/",
            ],
        )

    def test_customer_pages(self):
        client = Client()
        client.force_login(self.customer)
        self.assertRenders(
            client,
            [
                "/dashboard/customer/",
                "/cart/",
                "/orders/",
                "/orders/?status=active",
                f"/orders/{self.order.order_number}/",
                f"/orders/{self.order.order_number}/track/",
                f"/orders/{self.order.order_number}/invoice/",
                "/checkout/history/",
                "/accounts/profile/",
                "/accounts/addresses/",
                "/accounts/addresses/new/",
                "/accounts/notifications/",
                "/restaurants/favorites/",
                "/reviews/mine/",
            ],
        )

    def test_checkout_page_needs_a_filled_cart(self):
        client = Client()
        client.force_login(self.customer)
        self.assertEqual(client.get("/checkout/").status_code, 302)  # empty cart -> bounce back to cart
        fill_cart(self.customer, (self.food, 2))
        self.assertEqual(client.get("/checkout/").status_code, 200)
        fill_cart(self.customer)  # clean up for other tests

    def test_restaurant_pages(self):
        client = Client()
        client.force_login(self.owner)
        self.assertRenders(
            client,
            [
                "/restaurant-dashboard/",
                "/restaurant-dashboard/restaurant/",
                "/restaurant-dashboard/menu/",
                "/restaurant-dashboard/menu/new/",
                f"/restaurant-dashboard/menu/{self.food.pk}/edit/",
                "/restaurant-dashboard/categories/",
                "/restaurant-dashboard/orders/",
                "/restaurant-dashboard/orders/?status=new",
                f"/restaurant-dashboard/orders/{self.order.order_number}/",
                "/restaurant-dashboard/reviews/",
                "/restaurant-dashboard/offers/",
                "/restaurant-dashboard/sales/",
                "/restaurant-dashboard/profile/",
                "/accounts/profile/",
            ],
        )

    def test_delivery_pages(self):
        client = Client()
        client.force_login(self.rider)
        self.assertRenders(
            client,
            [
                "/delivery/",
                "/delivery/available/",
                f"/delivery/orders/{self.order.order_number}/",
                "/delivery/earnings/",
                "/delivery/history/",
                "/delivery/profile/",
            ],
        )

    def test_admin_pages(self):
        client = Client()
        client.force_login(self.admin)
        self.assertRenders(
            client,
            [
                "/admin-dashboard/",
                "/admin-dashboard/customers/",
                "/admin-dashboard/restaurant-owners/",
                "/admin-dashboard/restaurants/",
                f"/admin-dashboard/restaurants/{self.restaurant.pk}/",
                "/admin-dashboard/approvals/",
                "/admin-dashboard/delivery-boys/",
                "/admin-dashboard/delivery/",
                "/admin-dashboard/categories/",
                "/admin-dashboard/categories/new/",
                "/admin-dashboard/food/",
                "/admin-dashboard/orders/",
                f"/admin-dashboard/orders/{self.order.order_number}/",
                "/admin-dashboard/payments/",
                "/admin-dashboard/coupons/",
                "/admin-dashboard/coupons/new/",
                f"/admin-dashboard/coupons/{self.coupon.pk}/edit/",
                "/admin-dashboard/reviews/",
                "/admin-dashboard/reports/",
                "/admin-dashboard/settings/",
                "/accounts/profile/",
            ],
        )

    def test_django_admin_keeps_its_own_interface(self):
        """The custom FOODIES console must not shadow Django's admin templates."""
        client = Client()
        client.force_login(self.admin)
        body = client.get("/django-admin/").content.decode()
        self.assertIn("Site administration", body)
        self.assertNotIn("fd-shell", body)

    def test_error_pages_render(self):
        self.assertEqual(Client().get("/definitely-not-a-real-page/").status_code, 404)

    def test_statuses_are_shown_on_the_tracking_page(self):
        client = Client()
        client.force_login(self.customer)
        html = client.get(f"/orders/{self.order.order_number}/track/").content.decode()
        self.assertIn(self.order.order_number, html)
        self.assertIn(OrderStatus.ASSIGNED.label, html)

    def test_cancelled_order_tracking_page(self):
        from orders.services import cancel_order

        fill_cart(self.customer, (self.food, 1))
        order = create_order_from_cart(self.customer, self.address)
        cancel_order(order, actor=self.customer, reason="Test cancel")
        client = Client()
        client.force_login(self.customer)
        response = client.get(f"/orders/{order.order_number}/track/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.get(pk=order.pk).order_status, OrderStatus.CANCELLED)
