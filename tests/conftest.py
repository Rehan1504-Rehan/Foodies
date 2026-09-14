"""Shared test helpers for the FOODIES test-suite."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

from accounts.models import Address
from delivery.models import DeliveryBoyProfile
from menu.models import Category, FoodItem
from offers.models import Coupon
from restaurants.models import Restaurant

User = get_user_model()
PASSWORD = "Foodies@Test123"

#: 1x1 transparent GIF — cheap stand-in for uploaded photos in tests.
TINY_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def tiny_image(name="test.gif"):
    return ContentFile(TINY_GIF, name=name)


def make_user(email, role=User.Role.CUSTOMER, first_name="Test", last_name="User", **extra):
    return User.objects.create_user(
        email=email,
        password=PASSWORD,
        first_name=first_name,
        last_name=last_name,
        role=role,
        phone=extra.pop("phone", "9800000000"),
        **extra,
    )


def make_customer(email="customer@test.foodies", **extra):
    return make_user(email, User.Role.CUSTOMER, **extra)


def make_owner(email="owner@test.foodies", with_restaurant=True, approved=True, is_open=True, **extra):
    owner = make_user(email, User.Role.RESTAURANT_OWNER, first_name="Owner", **extra)
    if not with_restaurant:
        return owner
    slug = email.split("@")[0].replace(".", "-").replace("_", "-")
    restaurant = Restaurant.objects.create(
        owner=owner,
        name=f"Kitchen {slug}",
        slug=slug,
        description="Test kitchen",
        cuisine_type="North Indian, Chinese",
        phone="9800000001",
        address="1 Test Street",
        area="Test Area",
        city="Ahmedabad",
        state="Gujarat",
        pincode="380015",
        delivery_fee=Decimal("29.00"),
        minimum_order=Decimal("99.00"),
        delivery_time=30,
        is_approved=approved,
        is_open=is_open,
    )
    restaurant.logo.save("logo.gif", tiny_image("logo.gif"), save=True)
    restaurant.cover_image.save("cover.gif", tiny_image("cover.gif"), save=True)
    return owner


def make_rider(email="rider@test.foodies", approved=True, online=True, **extra):
    rider = make_user(email, User.Role.DELIVERY_BOY, first_name="Rider", **extra)
    DeliveryBoyProfile.objects.create(
        user=rider,
        vehicle_type=DeliveryBoyProfile.VehicleType.BIKE,
        vehicle_number="GJ01AA0001",
        license_number="DL-0000001",
        current_area="Test Area",
        is_approved=approved,
        availability_status=(
            DeliveryBoyProfile.Availability.ONLINE if online else DeliveryBoyProfile.Availability.OFFLINE
        ),
        earning_per_delivery=Decimal("40.00"),
    )
    return rider


def make_admin(email="admin@test.foodies"):
    return make_user(email, User.Role.ADMIN, first_name="Site", last_name="Admin")


def make_address(user, is_default=True, **extra):
    return Address.objects.create(
        user=user,
        full_name=f"{user.first_name} {user.last_name}".strip(),
        phone=user.phone or "9800000000",
        address_line="12 Test Apartments",
        area="Satellite",
        city="Ahmedabad",
        state="Gujarat",
        pincode="380015",
        landmark="Near Test Cross Road",
        address_type=Address.AddressType.HOME,
        is_default=is_default,
        **extra,
    )


def make_category(name="Test Category", **extra):
    slug = name.lower().replace(" ", "-")
    return Category.objects.create(name=name, slug=slug, icon="🍽️", **extra)


def make_food(restaurant, category=None, name="Test Dish", price="199.00", discount_price=None, available=True, **extra):
    if category is None:
        category = Category.objects.filter(name=f"Generic {restaurant.pk}").first()
        if category is None:
            category = make_category(name=f"Generic {restaurant.pk}")
    return FoodItem.objects.create(
        restaurant=restaurant,
        category=category,
        name=name,
        description="Tasty test dish",
        price=Decimal(str(price)),
        discount_price=Decimal(str(discount_price)) if discount_price else None,
        is_veg=True,
        is_available=available,
        preparation_time=15,
        image=tiny_image("dish.gif"),
        **extra,
    )


def fill_cart(user, *items):
    """``fill_cart(user, (food, qty), ...)`` — replace the server side cart contents."""
    from cart.models import Cart, CartItem

    cart, _ = Cart.objects.get_or_create(user=user)
    cart.cart_items.all().delete()
    for food, quantity in items:
        CartItem.objects.update_or_create(
            cart=cart,
            food_item=food,
            defaults={"quantity": quantity},
        )
    return cart


def make_coupon(code="TEST20", minimum="199.00", value="20", dtype="PERCENT", **extra):
    now = timezone.now()
    extra.setdefault("maximum_discount", Decimal("200.00"))
    extra.setdefault("is_active", True)
    return Coupon.objects.create(
        code=code,
        title=f"{code} test coupon",
        discount_type=dtype,
        discount_value=Decimal(str(value)),
        minimum_order=Decimal(str(minimum)),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        **extra,
    )
