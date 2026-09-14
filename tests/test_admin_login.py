"""Coverage for Django's built-in admin at /admin/ and the ADMIN credentials."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from tests.conftest import PASSWORD, make_customer

User = get_user_model()

ADMIN_ID = settings.ADMIN_LOGIN_ID
ADMIN_EMAIL = settings.ADMIN_LOGIN_EMAIL
ADMIN_PASSWORD = settings.ADMIN_LOGIN_PASSWORD


class DjangoAdminLoginTests(TestCase):
    """/admin/ is the stock Django admin with the standard login form."""

    def test_admin_sends_anonymous_visitors_to_the_login_page(self):
        response = self.client.get("/admin/")

        self.assertRedirects(response, "/admin/login/?next=/admin/")

    def test_admin_uses_the_standard_django_login_ui(self):
        response = self.client.get("/admin/login/?next=/admin/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django administration")
        self.assertContains(response, ">Username:</label>")
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        # The custom FOODIES admin login page is gone.
        self.assertNotContains(response, "fd-auth-wrap")
        self.assertNotContains(response, "Admin sign in")

    def test_admin_alias_credentials_open_the_django_admin(self):
        response = self.client.post(
            "/admin/login/?next=/admin/",
            {"username": ADMIN_ID, "password": ADMIN_PASSWORD},
        )

        self.assertRedirects(response, "/admin/")
        admin_user = User.objects.get(email=ADMIN_EMAIL)
        self.assertEqual(self.client.session["_auth_user_id"], str(admin_user.pk))
        self.assertContains(self.client.get("/admin/"), "Site administration")

    def test_canonical_admin_email_still_logs_in(self):
        response = self.client.post(
            "/admin/login/?next=/admin/",
            {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )

        self.assertRedirects(response, "/admin/")

    def test_invalid_credentials_are_rejected(self):
        response = self.client.post(
            "/admin/login/?next=/admin/",
            {"username": ADMIN_ID, "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Please enter the correct username and password for a staff account.",
        )

    def test_non_staff_accounts_cannot_log_into_the_admin(self):
        customer = make_customer("admin-login.customer@test.foodies")

        response = self.client.post(
            "/admin/login/?next=/admin/",
            {"username": customer.email, "password": PASSWORD},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Please enter the correct username and password for a staff account.",
        )

    def test_alias_login_also_opens_the_custom_admin_console(self):
        """The custom FOODIES admin console keeps working with the same account."""
        self.client.post(
            "/admin/login/?next=/admin/",
            {"username": ADMIN_ID, "password": ADMIN_PASSWORD},
        )

        response = self.client.get("/admin-dashboard/")

        self.assertEqual(response.status_code, 200)


class DjangoAdminAliasTests(TestCase):
    """/django-admin/ stays as a backward-compatible alias for /admin/."""

    def test_legacy_alias_redirects_to_the_new_location(self):
        response = self.client.get("/django-admin/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")

    def test_legacy_alias_keeps_deep_links_and_query_strings(self):
        response = self.client.get("/django-admin/menu/category/?o=1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/menu/category/?o=1")

    def test_legacy_login_alias_redirects_to_the_new_login(self):
        response = self.client.get("/django-admin/login/?next=/django-admin/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/login/?next=/django-admin/")
