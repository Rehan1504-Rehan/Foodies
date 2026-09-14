"""Order lifecycle: restaurant actions, delivery assignment, tracking, reviews."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from delivery.models import DeliveryAssignment, DeliveryEarning
from orders.models import Notification, Order, OrderStatus
from orders.services import assign_delivery_boy, cancel_order, complete_delivery, create_order_from_cart
from reviews.models import Review
from tests.conftest import (
    PASSWORD,
    fill_cart,
    make_address,
    make_admin,
    make_customer,
    make_food,
    make_owner,
    make_rider,
)


class LifecycleBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = make_customer("life.customer@test.foodies")
        cls.owner = make_owner("life.owner@test.foodies")
        cls.rider = make_rider("life.rider@test.foodies")
        cls.other_rider = make_rider("life.rider2@test.foodies")
        cls.admin = make_admin("life.admin@test.foodies")
        cls.restaurant = cls.owner.restaurants.first()
        cls.dish = make_food(cls.restaurant, name="Lifecycle Dish", price="200.00")
        cls.address = make_address(cls.customer)

    def place_order(self, **kwargs):
        fill_cart(self.customer, (self.dish, 1))
        return create_order_from_cart(self.customer, self.address, **kwargs)


class OrderStatusTransitionTests(LifecycleBase):
    def test_happy_path_transitions_are_enforced(self):
        order = self.place_order()
        self.assertTrue(order.can_transition_to(OrderStatus.CONFIRMED))
        self.assertFalse(order.can_transition_to(OrderStatus.DELIVERED))

        order.set_status(OrderStatus.CONFIRMED)
        order.set_status(OrderStatus.PREPARING)
        self.assertFalse(order.can_transition_to(OrderStatus.PLACED))
        order.set_status(OrderStatus.READY_FOR_PICKUP)
        assign_delivery_boy(order, self.rider, actor=self.admin)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.ASSIGNED)
        self.assertTrue(order.can_transition_to(OrderStatus.PICKED_UP))
        order.set_status(OrderStatus.PICKED_UP)
        order.set_status(OrderStatus.OUT_FOR_DELIVERY)
        self.assertFalse(order.can_transition_to(OrderStatus.CANCELLED))
        order.set_status(OrderStatus.DELIVERED)
        self.assertIsNotNone(order.delivered_at)
        self.assertFalse(order.can_transition_to(OrderStatus.OUT_FOR_DELIVERY))

    def test_status_history_is_recorded(self):
        order = self.place_order()
        self.assertEqual(order.status_history.count(), 1)  # PLACED is recorded at checkout
        order.set_status(OrderStatus.CONFIRMED, note="Accepted in kitchen", actor=self.owner)
        self.assertEqual(order.status_history.count(), 2)
        entry = order.status_history.order_by("-created_at").first()
        self.assertEqual(entry.status, OrderStatus.CONFIRMED)
        self.assertEqual(entry.created_by, self.owner)
        self.assertEqual(entry.note, "Accepted in kitchen")

    def test_customer_can_cancel_until_food_is_ready(self):
        order = self.place_order()
        cancel_order(order, actor=self.customer, reason="Changed my mind")
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CANCELLED)
        self.assertIsNotNone(order.cancelled_at)
        self.assertTrue(Notification.objects.filter(recipient=self.customer, order=order).exists())

    def test_delivered_order_cannot_be_cancelled(self):
        order = self.place_order()
        for status in (
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY_FOR_PICKUP,
            OrderStatus.ASSIGNED,
            OrderStatus.PICKED_UP,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED,
        ):
            order = Order.objects.get(pk=order.pk)
            order.set_status(status)
        with self.assertRaises(ValidationError):
            cancel_order(order, actor=self.customer, reason="too late")


class DeliveryAssignmentTests(LifecycleBase):
    def ready_order(self):
        order = self.place_order()
        order.set_status(OrderStatus.CONFIRMED)
        order.set_status(OrderStatus.PREPARING)
        order.set_status(OrderStatus.READY_FOR_PICKUP)
        return order

    def test_admin_assignment_is_recorded_and_notifies_partner(self):
        order = self.ready_order()
        assign_delivery_boy(order, self.rider, actor=self.admin)
        order.refresh_from_db()
        assignment = order.assignment
        self.assertEqual(assignment.delivery_boy, self.rider)
        self.assertEqual(order.order_status, OrderStatus.ASSIGNED)
        self.assertTrue(
            Notification.objects.filter(recipient=self.rider, order=order, title__icontains="assigned").exists()
        )

    def test_assignment_records_a_pending_earning_for_the_partner(self):
        order = self.ready_order()
        assign_delivery_boy(order, self.rider, actor=self.admin)
        earning = DeliveryEarning.objects.get(order=order)
        self.assertEqual(earning.status, DeliveryEarning.Status.PENDING)
        self.assertEqual(earning.amount, self.rider.delivery_profile.earning_per_delivery)

    def test_partner_completes_delivery_and_gets_paid(self):
        order = self.ready_order()
        assign_delivery_boy(order, self.rider, actor=self.admin)
        order.refresh_from_db()
        order.assignment.update_status(DeliveryAssignment.Status.PICKED_UP)
        order.set_status(OrderStatus.PICKED_UP)
        order.assignment.update_status(DeliveryAssignment.Status.OUT_FOR_DELIVERY)
        order.set_status(OrderStatus.OUT_FOR_DELIVERY)
        complete_delivery(order, actor=self.rider)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.DELIVERED)
        earning = DeliveryEarning.objects.get(order=order)
        self.assertEqual(earning.delivery_boy, self.rider)
        self.assertEqual(earning.amount, self.rider.delivery_profile.earning_per_delivery)

    def test_partner_cannot_transition_someone_elses_order_via_http(self):
        order = self.ready_order()
        assign_delivery_boy(order, self.other_rider, actor=self.admin)
        self.client.force_login(self.rider)
        response = self.client.post(reverse("delivery:update_status", args=[order.order_number, "PICKED_UP"]))
        self.assertIn(response.status_code, {403, 404})
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.ASSIGNED)

    def test_claim_flow_accepts_an_unassigned_ready_order(self):
        order = self.ready_order()
        self.client.force_login(self.rider)
        response = self.client.post(reverse("delivery:claim", args=[order.order_number]))
        self.assertIn(response.status_code, {302, 303})
        order.refresh_from_db()
        self.assertEqual(order.delivery_boy, self.rider)
        self.assertEqual(order.assignment.status, DeliveryAssignment.Status.ACCEPTED)

    def test_unapproved_or_offline_partner_cannot_claim(self):
        order = self.ready_order()
        offline = make_rider("offline.rider@test.foodies", online=False)
        self.client.force_login(offline)
        self.client.post(reverse("delivery:claim", args=[order.order_number]))
        order.refresh_from_db()
        self.assertIsNone(order.delivery_boy)

        pending = make_rider("pending.rider@test.foodies", approved=False)
        self.client.force_login(pending)
        self.client.post(reverse("delivery:claim", args=[order.order_number]))
        order.refresh_from_db()
        self.assertIsNone(order.delivery_boy)


class TrackingTests(LifecycleBase):
    def test_tracking_steps_follow_the_pipeline(self):
        order = self.place_order()
        steps = order.tracking_steps
        self.assertEqual(len(steps), len(OrderStatus.values) - 1)  # CANCELLED is not part of the flow
        labels = [label for label, state, _ in steps]
        self.assertEqual(labels[0], OrderStatus.PLACED.label)
        self.assertEqual(steps[0][1], "current")
        self.assertEqual(steps[1][1], "todo")

    def test_cancelled_order_has_short_tracker(self):
        order = self.place_order()
        cancel_order(order, actor=self.customer, reason="Test")
        order.refresh_from_db()
        states = [state for _, state, _ in order.tracking_steps]
        self.assertIn("cancelled", states)

    def test_track_api_returns_steps_for_the_owner_only(self):
        order = self.place_order()
        self.client.force_login(self.customer)
        response = self.client.get(f"/api/orders/{order.order_number}/track/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("steps", response.json())

        intruder = make_customer("intruder@test.foodies")
        self.client.force_login(intruder)
        self.assertEqual(self.client.get(f"/api/orders/{order.order_number}/track/").status_code, 404)


class ReviewRuleTests(LifecycleBase):
    def delivered_order(self):
        order = self.place_order()
        for status in (
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY_FOR_PICKUP,
            OrderStatus.ASSIGNED,
            OrderStatus.PICKED_UP,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED,
        ):
            order = Order.objects.get(pk=order.pk)
            order.set_status(status)
        return Order.objects.get(pk=order.pk)

    def test_only_delivered_orders_can_be_reviewed(self):
        order = self.place_order()
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("reviews:create", args=[order.order_number]),
            {"rating": 5, "comment": "Too early"},
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(Review.objects.filter(order=order).exists())

    def test_delivered_order_can_be_reviewed_once(self):
        order = self.delivered_order()
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("reviews:create", args=[order.order_number]),
            {"rating": 4, "comment": "Delicious and on time"},
        )
        self.assertIn(response.status_code, {200, 302, 303})
        review = Review.objects.get(order=order)
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.restaurant, self.restaurant)

        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.rating_count, 1)
        self.assertEqual(float(self.restaurant.rating), 4.0)

        # Second attempt must not create a duplicate review.
        self.client.post(
            reverse("reviews:create", args=[order.order_number]),
            {"rating": 1, "comment": "Trying again"},
        )
        self.assertEqual(Review.objects.filter(order=order).count(), 1)

    def test_owner_can_reply_to_a_review(self):
        order = self.delivered_order()
        review = Review.objects.create(
            customer=self.customer, restaurant=self.restaurant, order=order, rating=5, comment="Loved it"
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("dashboard:restaurant_reply_review", args=[review.pk]),
            {"reply": "Thank you for ordering with us!"},
        )
        self.assertIn(response.status_code, {302, 303})
        review.refresh_from_db()
        self.assertIn("Thank you", review.reply)
