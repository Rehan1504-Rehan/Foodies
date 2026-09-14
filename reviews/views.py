"""Restaurant reviews — only customers with a delivered order can review."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import customer_required
from orders.models import Order, OrderStatus
from reviews.models import Review


@customer_required
def create_review(request, order_number):
    order = get_object_or_404(
        Order.objects.select_related("restaurant"), order_number=order_number, customer=request.user
    )
    if order.order_status != OrderStatus.DELIVERED:
        messages.error(request, "You can only review an order after it has been delivered.")
        return redirect("orders:detail", order_number=order.order_number)
    if hasattr(order, "review"):
        messages.info(request, "You have already reviewed this order.")
        return redirect("orders:detail", order_number=order.order_number)

    if request.method == "POST":
        try:
            rating = int(request.POST.get("rating", 0))
        except (TypeError, ValueError):
            rating = 0
        comment = (request.POST.get("comment") or "").strip()[:1000]
        if rating not in range(1, 6):
            messages.error(request, "Please choose a rating between 1 and 5 stars.")
        else:
            try:
                Review.objects.create(
                    customer=request.user,
                    restaurant=order.restaurant,
                    order=order,
                    rating=rating,
                    comment=comment,
                )
                messages.success(request, "Thanks! Your review is live and helps other foodies.")
                return redirect("orders:detail", order_number=order.order_number)
            except IntegrityError:
                messages.info(request, "You have already reviewed this order.")
                return redirect("orders:detail", order_number=order.order_number)

    return render(request, "customer/review_form.html", {"order": order, "restaurant": order.restaurant})


@customer_required
def my_reviews(request):
    reviews = (
        Review.objects.filter(customer=request.user)
        .select_related("restaurant", "order")
        .order_by("-created_at")
    )
    return render(request, "customer/my_reviews.html", {"reviews": reviews})


@customer_required
def delete_review(request, pk):
    review = get_object_or_404(Review, pk=pk, customer=request.user)
    if request.method == "POST":
        restaurant = review.restaurant
        review.delete()
        restaurant.recalculate_rating()
        messages.success(request, "Review deleted.")
        return redirect("reviews:mine")
    return redirect("reviews:mine")
