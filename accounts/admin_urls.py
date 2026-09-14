"""Friendly admin entry-point routes.

The built-in Django model admin is intentionally exposed separately at
``/django-admin/``.  ``/admin/`` is the operator-facing FOODIES console login.
"""

from django.urls import path

from accounts import views

app_name = "admin_entry"

urlpatterns = [
    path("", views.AdminLoginView.as_view(), name="login"),
]
