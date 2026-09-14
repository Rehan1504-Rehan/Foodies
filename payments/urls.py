from django.urls import path

from payments import views

app_name = "payments"

urlpatterns = [
    path("", views.checkout, name="checkout"),
    path("history/", views.payment_history, name="history"),
    path("pay/<str:order_number>/", views.pay, name="pay"),
    path("pay/<str:order_number>/mock/", views.payment_mock, name="mock"),
    path("pay/<str:order_number>/razorpay/", views.payment_razorpay_callback, name="razorpay_callback"),
    path("webhook/razorpay/", views.razorpay_webhook, name="razorpay_webhook"),
]
