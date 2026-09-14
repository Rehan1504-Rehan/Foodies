from django.urls import path

from restaurants import views

app_name = "restaurants"

urlpatterns = [
    path("", views.restaurant_list, name="list"),
    path("favorites/", views.favorites, name="favorites"),
    path("<slug:slug>/", views.restaurant_detail, name="detail"),
    path("<slug:slug>/favorite/", views.toggle_favorite, name="toggle_favorite"),
]
