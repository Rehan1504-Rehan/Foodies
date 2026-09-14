from django.urls import path

from menu import views

app_name = "menu"

urlpatterns = [
    path("", views.category_list, name="list"),
    path("food/<int:pk>/favorite/", views.toggle_favorite_food, name="toggle_favorite_food"),
    path("<slug:slug>/", views.category_detail, name="category"),
]
