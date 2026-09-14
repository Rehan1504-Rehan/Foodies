from django.urls import path

from reviews import views

app_name = "reviews"

urlpatterns = [
    path("mine/", views.my_reviews, name="mine"),
    path("order/<str:order_number>/new/", views.create_review, name="create"),
    path("<int:pk>/delete/", views.delete_review, name="delete"),
]
