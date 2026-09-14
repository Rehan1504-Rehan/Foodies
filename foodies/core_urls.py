"""Public FOODIES website routes (namespace: ``core``)."""

from django.urls import path

from foodies import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("offers/", views.offers, name="offers"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("healthz/", views.health, name="health"),
]
