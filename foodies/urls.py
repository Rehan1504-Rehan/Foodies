"""FOODIES root URL configuration.

``/``                        public customer website (namespace: core)
``/accounts/``               authentication, profiles, addresses
``/restaurants/ /cart/ ...``  customer modules
``/admin/``                 admin login (user ID: ADMIN)
``/admin-dashboard/``        custom FOODIES admin interface
``/restaurant-dashboard/``   restaurant owner interface
``/delivery/``               delivery partner interface
``/api/``                    Django REST Framework API
``/django-admin/``           Django's built-in admin (model level operations)
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

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
    # Friendly admin login at /admin/; Django's model admin stays isolated at
    # /django-admin/ so the two interfaces do not shadow each other.
    path("admin/", include("accounts.admin_urls")),
    path("django-admin/", admin.site.urls),
    path("api/", include("foodies.api_urls")),
]

handler400 = "foodies.views.error_400"
handler403 = "foodies.views.error_403"
handler404 = "foodies.views.error_404"
handler500 = "foodies.views.error_500"

# Uploaded media (food photos, logos, profile pictures).
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
