"""FOODIES root URL configuration.

``/``                        public customer website (namespace: core)
``/accounts/``               authentication, profiles, addresses
``/restaurants/ /cart/ ...``  customer modules
``/admin/``                  Django's built-in admin (login: ADMIN)
``/admin-dashboard/``        custom FOODIES admin console
``/restaurant-dashboard/``   restaurant owner interface
``/delivery/``               delivery partner interface
``/api/``                    Django REST Framework API
``/django-admin/``           backward-compatible redirect to ``/admin/``
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from accounts.forms import AdminAuthenticationForm

# The FOODIES user model signs in with e-mail addresses; let operators type
# the friendly ADMIN user ID on the login form as an alias for the canonical
# admin account (see ADMIN_LOGIN_* in settings.py).  Everything else about
# /admin/ is stock Django admin: admin.site.urls, admin/login.html and the
# normal staff permission checks.
admin.site.login_form = AdminAuthenticationForm

urlpatterns = [
    # ---------------------------------------------------------------- core
    path("", include("foodies.core_urls")),

    # ------------------------------------------------------------ modules
    path("accounts/", include("accounts.urls")),
    path("restaurants/", include("restaurants.urls")),
    path("categories/", include("menu.urls")),
    path("cart/", include("cart.urls")),
    path("checkout/", include("payments.urls")),
    path("orders/", include("orders.urls")),
    path("reviews/", include("reviews.urls")),
    path("delivery/", include("delivery.urls")),

    # --------------------------------------------------------- dashboards
    # /admin-dashboard/, /restaurant-dashboard/, /customer/, /dashboard/
    path("", include("dashboard.urls")),

    # -------------------------------------------------------------- admin
    # Django's built-in admin with its standard login UI at /admin/.
    path("admin/", admin.site.urls),
    # Backward-compatible alias for the previous /django-admin/ location.
    # Including admin.site.urls twice would duplicate the "admin" URL
    # namespace (system check urls.W005), so the legacy path redirects
    # instead — keeping any sub-path and query string intact.
    re_path(
        r"^django-admin/(?P<rest>.*)$",
        RedirectView.as_view(url="/admin/%(rest)s", query_string=True),
        name="django_admin_alias",
    ),
    path("api/", include("foodies.api_urls")),
]

handler400 = "foodies.views.error_400"
handler403 = "foodies.views.error_403"
handler404 = "foodies.views.error_404"
handler500 = "foodies.views.error_500"

# Uploaded media (food photos, logos, profile pictures).
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
