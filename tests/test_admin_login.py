"""Coverage for the dedicated /admin/ entry point and ADMIN credentials."""

from django.test import TestCase

from accounts.models import User
from tests.conftest import PASSWORD, make_customer


class AdminLoginTests(TestCase):
    def test_admin_login_page_is_available(self):
        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin sign in")
        self.assertContains(response, "User ID")

    def test_requested_admin_credentials_open_the_admin_console(self):
        response = self.client.post(
            "/admin/",
            {"user_id": "ADMIN", "password": "Password@123"},
        )

        self.assertRedirects(response, "/admin-dashboard/")
        self.assertEqual(self.client.session["_auth_user_id"], str(User.objects.get(email="admin@foodies.test").pk))
        self.assertEqual(self.client.get("/admin-dashboard/").status_code, 200)

    def test_invalid_or_non_admin_credentials_are_rejected(self):
        invalid = self.client.post(
            "/admin/",
            {"user_id": "ADMIN", "password": "wrong-password"},
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "Incorrect admin user ID or password.")

        customer = make_customer("admin-login.customer@test.foodies")
        non_admin = self.client.post(
            "/admin/",
            {"user_id": customer.email, "password": PASSWORD},
        )
        self.assertEqual(non_admin.status_code, 200)
        self.assertContains(non_admin, "This account does not have admin access.")
