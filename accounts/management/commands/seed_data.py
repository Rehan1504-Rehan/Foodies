"""Seed the FOODIES database with realistic demo data.

    python manage.py seed_data            # safe: skips existing records
    python manage.py seed_data --flush    # wipe demo data first

Creates sample customers, restaurant owners, restaurants (approved + pending),
delivery partners, categories, dishes, coupons, addresses, orders across the
whole status pipeline, reviews, notifications and delivery earnings.
"""

import random
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Address, User
from delivery.models import DeliveryAssignment, DeliveryBoyProfile, DeliveryEarning
from menu.models import Category, FoodItem
from offers.models import Coupon
from orders.models import Notification, Order, OrderItem, OrderStatus, PaymentStatus
from orders.services import assign_delivery_boy, complete_delivery, notify
from payments.models import Payment
from payments.services import create_payment_record
from restaurants.models import Restaurant
from reviews.models import Review

SEED_IMAGE_DIR = Path(settings.BASE_DIR) / "static" / "images" / "seed"

PASSWORD = "Foodies@123"
ADMIN_PASSWORD = "Admin@12345"

CATEGORIES = [
    ("Pizza", "🍕", "Cheesy, wood-fired and loaded with toppings"),
    ("Burger", "🍔", "Juicy patties between toasted buns"),
    ("Biryani", "🍛", "Slow-cooked dum biryani and rice bowls"),
    ("Chinese", "🥡", "Indo-Chinese noodles, manchurian and more"),
    ("Gujarati", "🥘", "Traditional thali, farsan and shaak"),
    ("South Indian", "🥞", "Dosa, idli, uttapam and filter coffee"),
    ("North Indian", "🍲", "Rich curries, tandoori breads and gravies"),
    ("Desserts", "🍰", "Sweet endings and festive treats"),
    ("Beverages", "🥤", "Coolers, shakes, chai and coffee"),
    ("Fast Food", "🌯", "Quick bites, rolls, wraps and snacks"),
    ("Thali", "🍽️", "Complete platters with everything included"),
    ("Healthy Food", "🥗", "Salads, bowls and guilt-free plates"),
]

RESTAURANTS = [
    {
        "name": "Spice Route Kitchen",
        "owner": ("Priya", "Mehta", "owner@foodies.test", "9825011111"),
        "cuisine_type": "North Indian, Biryani, Thali",
        "city": "Ahmedabad", "area": "Satellite",
        "address": "12, Shivranjani Cross Road",
        "pincode": "380015", "delivery_time": 32, "delivery_fee": "29.00", "minimum_order": "149.00",
        "description": "Slow-cooked North Indian curries, dum biryani and hearty thalis from a family kitchen running since 1998.",
        "cover": "cover-northindian.jpg", "logo": "logo-spice.jpg", "approved": True,
    },
    {
        "name": "Slice of Naples",
        "owner": ("Marco", "D'Souza", "marco@foodies.test", "9825022222"),
        "cuisine_type": "Pizza, Fast Food, Beverages",
        "city": "Ahmedabad", "area": "Bodakdev",
        "address": "44, Corporate Road",
        "pincode": "380054", "delivery_time": 25, "delivery_fee": "35.00", "minimum_order": "199.00",
        "description": "Hand-stretched sourdough pizza baked in a stone oven, with Italian-imported cheese and fresh basil.",
        "cover": "cover-pizza.jpg", "logo": "logo-pizza.jpg", "approved": True,
    },
    {
        "name": "Dosa Junction",
        "owner": ("Lakshmi", "Iyer", "lakshmi@foodies.test", "9825033333"),
        "cuisine_type": "South Indian, Healthy Food, Beverages",
        "city": "Ahmedabad", "area": "Maninagar",
        "address": "8, Kankaria Road",
        "pincode": "380008", "delivery_time": 28, "delivery_fee": "25.00", "minimum_order": "99.00",
        "description": "Crisp dosas, fluffy idlis and authentic filter coffee served the way it is done in Chennai.",
        "cover": "cover-southindian.jpg", "logo": "logo-dosa.jpg", "approved": True,
    },
    {
        "name": "Wok & Roll",
        "owner": ("Chen", "Wei", "chen@foodies.test", "9825044444"),
        "cuisine_type": "Chinese, Fast Food",
        "city": "Gandhinagar", "area": "Sector 11",
        "address": "Shop 3, Infocity Mall",
        "pincode": "382011", "delivery_time": 30, "delivery_fee": "30.00", "minimum_order": "129.00",
        "description": "Wok-tossed noodles, spicy manchurian and street-style Chinese done the Indian way.",
        "cover": "cover-chinese.jpg", "logo": "logo-wok.jpg", "approved": True,
    },
    {
        "name": "Gujarati Rasoi",
        "owner": ("Bhavna", "Patel", "bhavna@foodies.test", "9825055555"),
        "cuisine_type": "Gujarati, Thali, Desserts",
        "city": "Ahmedabad", "area": "Vastrapur",
        "address": "21, Mansi Circle",
        "pincode": "380015", "delivery_time": 35, "delivery_fee": "29.00", "minimum_order": "179.00",
        "description": "Unlimited-style Gujarati thali with farsan, seasonal shaak, dal, kadhi and hand-rolled rotis.",
        "cover": "cover-gujarati.jpg", "logo": "logo-rasoi.jpg", "approved": True,
    },
    {
        "name": "Sweet Tooth Patisserie",
        "owner": ("Aditi", "Kapoor", "aditi@foodies.test", "9825066666"),
        "cuisine_type": "Desserts, Beverages, Fast Food",
        "city": "Ahmedabad", "area": "Prahladnagar",
        "address": "5, Titanium Square",
        "pincode": "380015", "delivery_time": 22, "delivery_fee": "25.00", "minimum_order": "99.00",
        "description": "Fresh cream cakes, brownies and artisan desserts baked every morning.",
        "cover": "cover-dessert.jpg", "logo": "logo-sweet.jpg", "approved": True,
    },
    {
        "name": "Urban Clucker",
        "owner": ("Rohit", "Nair", "rohit@foodies.test", "9825077777"),
        "cuisine_type": "Burger, Fast Food, Beverages",
        "city": "Ahmedabad", "area": "SG Highway",
        "address": "99, One42 Mall",
        "pincode": "380054", "delivery_time": 26, "delivery_fee": "35.00", "minimum_order": "149.00",
        "description": "Crispy fried chicken burgers, loaded fries and thick shakes — comfort food at its best.",
        "cover": "cover-burger.jpg", "logo": "logo-clucker.jpg", "approved": True,
    },
    {
        "name": "Green Bowl Co.",
        "owner": ("Sneha", "Rao", "sneha@foodies.test", "9825088888"),
        "cuisine_type": "Healthy Food, South Indian",
        "city": "Ahmedabad", "area": "Bopal",
        "address": "17, South Bopal Circle",
        "pincode": "380058", "delivery_time": 27, "delivery_fee": "29.00", "minimum_order": "149.00",
        "description": "Cold-pressed juices, millet bowls and protein salads built by nutritionists.",
        "cover": "cover-healthy.jpg", "logo": "logo-green.jpg", "approved": False,  # pending approval demo
    },
]

MENU = {
    "Spice Route Kitchen": [
        ("Biryani", "Hyderabadi Chicken Biryani", "Dum-cooked basmati rice layered with spiced chicken, saffron and fried onions.", 320, 269, False, 25, "biryani.jpg"),
        ("Biryani", "Veg Dum Biryani", "Fragrant rice with seasonal vegetables, mint and whole spices.", 260, 219, True, 22, "biryani.jpg"),
        ("North Indian", "Paneer Butter Masala", "Cottage cheese simmered in a silky tomato-cashew gravy.", 280, None, True, 18, "paneer.jpg"),
        ("North Indian", "Dal Makhani", "Black lentils slow-cooked overnight with butter and cream.", 240, 199, True, 20, "dal.jpg"),
        ("Thali", "Special Gujarati Thali", "Roti, rice, dal, kadhi, two shaak, farsan, sweet and chaas.", 340, 299, True, 15, "thali.jpg"),
        ("North Indian", "Butter Naan", "Tandoor-baked naan brushed with butter.", 60, None, True, 8, "naan.jpg"),
        ("Desserts", "Gulab Jamun (2 pcs)", "Warm milk dumplings soaked in cardamom syrup.", 90, None, True, 5, "dessert.jpg"),
        ("Beverages", "Masala Chaas", "Spiced buttermilk with roasted cumin and curry leaves.", 60, None, True, 4, "beverage.jpg"),
    ],
    "Slice of Naples": [
        ("Pizza", "Margherita Classic", "San Marzano tomato, fior di latte mozzarella and basil.", 299, 249, True, 18, "pizza.jpg"),
        ("Pizza", "Farmhouse Pizza", "Capsicum, onion, corn, olives and mushroom on a cheesy base.", 379, 329, True, 20, "pizza.jpg"),
        ("Pizza", "Peri Peri Chicken Pizza", "Spicy peri peri chicken with jalapenos and red onion.", 429, 379, False, 22, "pizza.jpg"),
        ("Fast Food", "Garlic Bread with Cheese", "Wood-fired garlic bread loaded with mozzarella.", 179, None, True, 12, "naan.jpg"),
        ("Beverages", "Cold Coffee", "Chilled espresso blended with milk and vanilla ice cream.", 149, 129, True, 8, "beverage.jpg"),
        ("Desserts", "Choco Lava Cake", "Warm chocolate cake with a molten centre.", 149, None, True, 10, "dessert.jpg"),
    ],
    "Dosa Junction": [
        ("South Indian", "Masala Dosa", "Crisp rice crepe with spiced potato filling, sambar and chutney.", 150, 129, True, 14, "dosa.jpg"),
        ("South Indian", "Ghee Roast Dosa", "Extra crisp dosa roasted in pure ghee.", 180, None, True, 16, "dosa.jpg"),
        ("South Indian", "Idli Sambar (3 pcs)", "Steamed rice cakes with sambar and coconut chutney.", 110, 95, True, 10, "idli.jpg"),
        ("South Indian", "Onion Uttapam", "Thick pancake topped with onion, chilli and coriander.", 160, None, True, 15, "dosa.jpg"),
        ("Healthy Food", "Millet Khichdi Bowl", "Foxtail millet, moong dal and vegetables with ghee tempering.", 210, 189, True, 18, "healthy.jpg"),
        ("Beverages", "Filter Coffee", "Traditional South Indian filter decoction with frothy milk.", 70, None, True, 5, "beverage.jpg"),
    ],
    "Wok & Roll": [
        ("Chinese", "Hakka Noodles", "Wok-tossed noodles with julienned vegetables and soy.", 190, 169, True, 14, "noodles.jpg"),
        ("Chinese", "Chicken Manchurian", "Crispy chicken tossed in a tangy Indo-Chinese sauce.", 260, 229, False, 18, "noodles.jpg"),
        ("Chinese", "Veg Fried Rice", "Classic fried rice with spring onion and white pepper.", 180, None, True, 13, "noodles.jpg"),
        ("Fast Food", "Crispy Spring Rolls (4 pcs)", "Golden rolls stuffed with vegetables and glass noodles.", 160, 139, True, 12, "noodles.jpg"),
        ("Beverages", "Lemon Iced Tea", "Freshly brewed tea with lemon and mint.", 110, None, True, 5, "beverage.jpg"),
    ],
    "Gujarati Rasoi": [
        ("Gujarati", "Gujarati Thali (Regular)", "Farsan, two shaak, dal, kadhi, roti, rice, pickle and sweet.", 260, 229, True, 15, "thali.jpg"),
        ("Gujarati", "Undhiyu", "Winter special mixed vegetable curry with muthiya.", 240, None, True, 22, "thali.jpg"),
        ("Thali", "Deluxe Thali", "Everything in the regular thali plus paneer shaak and two sweets.", 340, 299, True, 18, "thali.jpg"),
        ("Fast Food", "Khaman Dhokla", "Steamed gram flour cakes with mustard tempering.", 110, 95, True, 8, "thali.jpg"),
        ("Desserts", "Shrikhand", "Strained yoghurt sweetened with saffron and cardamom.", 120, None, True, 5, "dessert.jpg"),
    ],
    "Sweet Tooth Patisserie": [
        ("Desserts", "Belgian Chocolate Brownie", "Fudgy brownie with Belgian dark chocolate chunks.", 160, 139, True, 6, "dessert.jpg"),
        ("Desserts", "Red Velvet Pastry", "Classic red velvet with cream cheese frosting.", 180, None, True, 5, "dessert.jpg"),
        ("Desserts", "Tiramisu Cup", "Espresso-soaked ladyfingers with mascarpone cream.", 220, 189, True, 8, "dessert.jpg"),
        ("Beverages", "Belgian Hot Chocolate", "Thick hot chocolate made with real cocoa.", 180, None, True, 6, "beverage.jpg"),
    ],
    "Urban Clucker": [
        ("Burger", "Crispy Chicken Burger", "Fried chicken fillet, lettuce and smoky mayo in a brioche bun.", 220, 189, False, 12, "burger.jpg"),
        ("Burger", "Double Cheese Veg Burger", "Two patties with double cheese and house sauce.", 200, 179, True, 12, "burger.jpg"),
        ("Fast Food", "Loaded Cheese Fries", "Fries topped with cheese sauce, jalapeno and herbs.", 180, None, True, 10, "burger.jpg"),
        ("Beverages", "Oreo Thick Shake", "Blended Oreo shake topped with whipped cream.", 190, 169, True, 7, "beverage.jpg"),
        ("Fast Food", "Peri Peri Chicken Wrap", "Grilled chicken, veggies and peri peri sauce in a tortilla.", 210, None, False, 14, "burger.jpg"),
    ],
    "Green Bowl Co.": [
        ("Healthy Food", "Quinoa Protein Bowl", "Quinoa, chickpeas, corn, avocado and lemon dressing.", 280, 249, True, 15, "healthy.jpg"),
        ("Healthy Food", "Paneer Tikka Salad", "Grilled paneer, greens, cherry tomato and mint dressing.", 250, None, True, 14, "healthy.jpg"),
        ("Healthy Food", "Millet Upma Bowl", "Barnyard millet upma with peanuts and vegetables.", 190, 169, True, 16, "healthy.jpg"),
    ],
}

CUSTOMERS = [
    ("Rahul", "Sharma", "rahul@foodies.test", "9876543210", "Satellite", "380015"),
    ("Ananya", "Desai", "ananya@foodies.test", "9876543211", "Bopal", "380058"),
    ("Vikram", "Singh", "vikram@foodies.test", "9876543212", "Bodakdev", "380054"),
    ("Meera", "Joshi", "meera@foodies.test", "9876543213", "Maninagar", "380008"),
    ("Karan", "Shah", "karan@foodies.test", "9876543214", "Vastrapur", "380015"),
]

RIDERS = [
    ("Arjun", "Yadav", "rider@foodies.test", "9765011111", "BIKE", "GJ01AB1234", "Satellite"),
    ("Sunil", "Kumar", "sunil@foodies.test", "9765022222", "SCOOTER", "GJ01CD5678", "Maninagar"),
    ("Imran", "Sheikh", "imran@foodies.test", "9765033333", "EV", "GJ01EF9012", "Bopal"),
    ("Deepak", "Verma", "deepak@foodies.test", "9765044444", "BIKE", "GJ01GH3456", "Bodakdev"),
]

# (code, title, discount_type, value, minimum_order, maximum_discount, valid_days, first_order_only)
COUPONS = [
    ("WELCOME50", "Flat ₹50 off your first FOODIES order", "FIXED", 50, 199, 50, 30, True),
    ("FOODIE20", "20% off on orders above ₹349", "PERCENT", 20, 349, 150, 45, False),
    ("BIRYANI100", "₹100 off on orders above ₹599", "FIXED", 100, 599, 100, 20, False),
    ("TASTY30", "30% off up to ₹120 on orders above ₹249", "PERCENT", 30, 249, 120, 15, False),
    ("WEEKEND99", "₹99 off this weekend", "FIXED", 99, 399, 99, 10, False),
    ("HEALTHY15", "15% off on healthy bowls", "PERCENT", 15, 149, 90, 60, False),
]


class Command(BaseCommand):
    help = "Seed the FOODIES database with demo customers, restaurants, menus, orders and reviews."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Delete existing demo data first.")
        parser.add_argument("--orders", type=int, default=28, help="How many sample orders to create.")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(1504)
        if options["flush"]:
            self.stdout.write(self.style.WARNING("Flushing existing demo data…"))
            self._flush()

        categories = self._seed_categories()
        admin = self._seed_admin()
        customers = self._seed_customers()
        owners = self._seed_owners()
        restaurants = self._seed_restaurants(owners)
        self._seed_menu(restaurants, categories)
        riders = self._seed_riders()
        coupons = self._seed_coupons(restaurants)
        self._seed_orders(customers, restaurants, riders, coupons, options["orders"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("FOODIES demo data is ready! 🍔"))
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Login credentials"))
        self.stdout.write("  Admin            admin@foodies.test   / Admin@12345")
        self.stdout.write("  Customer         rahul@foodies.test   / Foodies@123")
        self.stdout.write("  Restaurant owner owner@foodies.test   / Foodies@123")
        self.stdout.write("  Delivery partner rider@foodies.test   / Foodies@123")
        self.stdout.write("")
        self.stdout.write(f"  {User.objects.count()} users • {Restaurant.objects.count()} restaurants • "
                          f"{FoodItem.objects.count()} dishes • {Order.objects.count()} orders")

    # ------------------------------------------------------------------ steps
    def _flush(self):
        for model in (DeliveryEarning, DeliveryAssignment, Payment, Review, OrderItem, Notification, Order):
            model.objects.all().delete()
        Coupon.objects.all().delete()
        FoodItem.objects.all().delete()
        Restaurant.objects.all().delete()
        User.objects.filter(email__endswith="@foodies.test").delete()

    def _image(self, filename):
        """Return a ContentFile for a bundled demo image, or None when missing."""
        path = SEED_IMAGE_DIR / filename
        if not path.exists():
            return None
        return ContentFile(path.read_bytes(), name=filename)

    def _seed_categories(self):
        self.stdout.write("• Categories…")
        created = {}
        for index, (name, icon, description) in enumerate(CATEGORIES):
            category, _ = Category.objects.get_or_create(
                name=name,
                defaults={"icon": icon, "description": description, "display_order": index},
            )
            created[name] = category
        return created

    def _seed_admin(self):
        self.stdout.write("• Admin account…")
        admin = User.objects.filter(email="admin@foodies.test").first()
        if not admin:
            admin = User.objects.create_superuser(
                email="admin@foodies.test", password=ADMIN_PASSWORD, first_name="Aarav", last_name="Boss",
                phone="9000000000", role="ADMIN",
            )
        return admin

    def _seed_customers(self):
        self.stdout.write("• Customers…")
        customers = []
        for first, last, email, phone, area, pincode in CUSTOMERS:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"first_name": first, "last_name": last, "phone": phone,
                          "role": "CUSTOMER", "email_verified": True, "is_active": True},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            if not user.addresses.exists():
                Address.objects.create(
                    user=user, full_name=f"{first} {last}", phone=phone,
                    address_line=f"{random.randint(1, 90)}, Sunrise Residency",
                    area=area, city="Ahmedabad", state="Gujarat", pincode=pincode,
                    landmark="Near City Centre Mall", address_type="HOME", is_default=True,
                )
                Address.objects.create(
                    user=user, full_name=f"{first} {last}", phone=phone,
                    address_line=f"{random.randint(100, 500)}, Tech Park Tower B",
                    area=area, city="Ahmedabad", state="Gujarat", pincode=pincode,
                    address_type="WORK",
                )
            customers.append(user)
        return customers

    def _seed_owners(self):
        self.stdout.write("• Restaurant owners…")
        owners = {}
        for entry in RESTAURANTS:
            first, last, email, phone = entry["owner"]
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"first_name": first, "last_name": last, "phone": phone, "role": "RESTAURANT_OWNER"},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            owners[entry["name"]] = user
        return owners

    def _seed_restaurants(self, owners):
        self.stdout.write("• Restaurants…")
        restaurants = {}
        for entry in RESTAURANTS:
            owner = owners[entry["name"]]
            restaurant, created = Restaurant.objects.get_or_create(
                name=entry["name"],
                defaults={
                    "owner": owner,
                    "description": entry["description"],
                    "phone": entry["owner"][3],
                    "email": entry["owner"][2],
                    "address": entry["address"],
                    "area": entry["area"],
                    "city": entry["city"],
                    "state": "Gujarat",
                    "pincode": entry["pincode"],
                    "cuisine_type": entry["cuisine_type"],
                    "delivery_time": entry["delivery_time"],
                    "delivery_fee": Decimal(entry["delivery_fee"]),
                    "minimum_order": Decimal(entry["minimum_order"]),
                    "is_approved": entry["approved"],
                    "is_active": True,
                    "is_open": entry["approved"],
                },
            )
            if created:
                cover = self._image(entry["cover"])
                logo = self._image(entry["logo"])
                if cover:
                    restaurant.cover_image.save(entry["cover"], cover, save=False)
                if logo:
                    restaurant.logo.save(entry["logo"], logo, save=False)
                restaurant.save()
            restaurants[entry["name"]] = restaurant
        return restaurants

    def _seed_menu(self, restaurants, categories):
        self.stdout.write("• Menu items…")
        for restaurant_name, items in MENU.items():
            restaurant = restaurants[restaurant_name]
            for category_name, name, description, price, discount, is_veg, prep, image in items:
                food, created = FoodItem.objects.get_or_create(
                    restaurant=restaurant,
                    name=name,
                    defaults={
                        "category": categories[category_name],
                        "description": description,
                        "price": Decimal(str(price)),
                        "discount_price": Decimal(str(discount)) if discount else None,
                        "is_veg": is_veg,
                        "is_available": True,
                        "is_recommended": discount is not None,
                        "preparation_time": prep,
                        "order_count": random.randint(0, 40),
                        "rating": Decimal(str(round(random.uniform(3.8, 4.9), 2))),
                    },
                )
                if created:
                    image_file = self._image(image)
                    if image_file:
                        food.image.save(image, image_file, save=False)
                        food.save()

    def _seed_riders(self):
        self.stdout.write("• Delivery partners…")
        riders = []
        for index, (first, last, email, phone, vehicle, number, area) in enumerate(RIDERS):
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"first_name": first, "last_name": last, "phone": phone, "role": "DELIVERY_BOY"},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            profile, _ = DeliveryBoyProfile.objects.get_or_create(
                user=user,
                defaults={
                    "vehicle_type": vehicle,
                    "vehicle_number": number,
                    "license_number": f"DL-{random.randint(1000000, 9999999)}",
                    "current_area": area,
                    "is_approved": True,
                    "availability_status": "ONLINE" if index < 2 else "OFFLINE",
                    "earning_per_delivery": Decimal(str(settings.DEFAULT_DELIVERY_EARNING + index * 5)),
                },
            )
            riders.append(profile)
        return list(DeliveryBoyProfile.objects.filter(user__email__in=[r[2] for r in RIDERS]))

    def _seed_coupons(self, restaurants):
        self.stdout.write("• Coupons…")
        now = timezone.now()
        coupons = []
        for code, title, dtype, value, minimum, maximum, days, first_only in COUPONS:
            coupon, _ = Coupon.objects.get_or_create(
                code=code,
                defaults={
                    "title": title,
                    "description": f"{title}. Apply at checkout on FOODIES.",
                    "discount_type": dtype,
                    "discount_value": Decimal(str(value)),
                    "minimum_order": Decimal(str(minimum)),
                    "maximum_discount": Decimal(str(maximum)),
                    "valid_from": now - timedelta(days=2),
                    "valid_until": now + timedelta(days=days),
                    "usage_limit": 500,
                    "per_user_limit": 1 if first_only else 3,
                    "first_order_only": bool(first_only),
                    "is_active": True,
                },
            )
            coupons.append(coupon)

        # One restaurant-specific offer
        restaurant = restaurants.get("Slice of Naples")
        if restaurant:
            Coupon.objects.get_or_create(
                code="PIZZA25",
                defaults={
                    "title": "25% off at Slice of Naples",
                    "description": "Exclusive to Slice of Naples — 25% off up to ₹150.",
                    "discount_type": "PERCENT",
                    "discount_value": Decimal("25"),
                    "minimum_order": Decimal("299"),
                    "maximum_discount": Decimal("150"),
                    "valid_from": now - timedelta(days=1),
                    "valid_until": now + timedelta(days=21),
                    "usage_limit": 200,
                    "restaurant": restaurant,
                    "is_active": True,
                },
            )
        return coupons

    def _seed_orders(self, customers, restaurants, riders, coupons, count):
        self.stdout.write("• Orders, payments, reviews…")
        approved = [r for r in restaurants.values() if r.is_approved]
        if not approved or Order.objects.exists():
            self.stdout.write("  (orders already exist — skipping order generation)")
            return

        statuses = (
            [OrderStatus.DELIVERED] * 16
            + [OrderStatus.PLACED] * 3
            + [OrderStatus.CONFIRMED] * 2
            + [OrderStatus.PREPARING] * 2
            + [OrderStatus.READY_FOR_PICKUP] * 2
            + [OrderStatus.OUT_FOR_DELIVERY] * 2
            + [OrderStatus.CANCELLED] * 1
        )

        for index in range(count):
            customer = random.choice(customers)
            restaurant = random.choice(approved)
            address = customer.addresses.first()
            items = list(restaurant.food_items.all()[:6])
            if not items or address is None:
                continue
            chosen = random.sample(items, k=min(len(items), random.randint(1, 3)))

            subtotal = sum((item.final_price * 1 for item in chosen), Decimal("0.00"))
            quantities = [random.randint(1, 2) for _ in chosen]
            subtotal = sum((item.final_price * qty for item, qty in zip(chosen, quantities)), Decimal("0.00"))
            food_discount = sum(((item.price - item.final_price) * qty for item, qty in zip(chosen, quantities)), Decimal("0.00"))
            delivery_fee = Decimal("0.00") if subtotal >= Decimal(str(settings.FREE_DELIVERY_ABOVE)) else restaurant.delivery_fee
            tax = (subtotal * Decimal(str(settings.TAX_RATE))).quantize(Decimal("0.01"))
            platform_fee = Decimal(str(settings.PLATFORM_FEE))

            coupon = None
            coupon_discount = Decimal("0.00")
            if index % 4 == 0:
                for candidate in coupons:
                    ok, _ = candidate.validate_for(customer, subtotal, restaurant)
                    if ok:
                        coupon = candidate
                        coupon_discount = candidate.calculate_discount(subtotal)
                        break

            total = subtotal - coupon_discount + delivery_fee + tax + platform_fee
            status = statuses[index % len(statuses)]
            created = timezone.now() - timedelta(days=random.randint(0, 20), hours=random.randint(0, 20))
            payment_method = random.choice(["COD", "COD", "RAZORPAY", "MOCK"])

            order = Order.objects.create(
                customer=customer,
                restaurant=restaurant,
                delivery_address=address,
                delivery_address_text=address.full_address,
                customer_name=address.full_name,
                customer_phone=address.phone,
                subtotal=subtotal,
                discount=food_discount.quantize(Decimal("0.01")),
                delivery_fee=delivery_fee,
                tax=tax,
                platform_fee=platform_fee,
                coupon=coupon,
                coupon_discount=coupon_discount,
                total_amount=total.quantize(Decimal("0.01")),
                order_status=OrderStatus.PLACED,
                payment_status=PaymentStatus.COD if payment_method == "COD" else PaymentStatus.PAID,
                created_at=created,
            )
            Order.objects.filter(pk=order.pk).update(created_at=created)

            for item, qty in zip(chosen, quantities):
                OrderItem.objects.create(
                    order=order, food_item=item, food_name=item.name, category_name=item.category.name,
                    is_veg=item.is_veg, price=item.final_price, mrp=item.price, quantity=qty,
                )

            payment = create_payment_record(order, payment_method)
            if payment_method != "COD":
                payment.status = Payment.Status.SUCCESS
                payment.gateway_response = {"mode": "seed", "status": "captured"}
                payment.save(update_fields=["status", "gateway_response"])

            # Walk the order through the pipeline with correct timestamps.
            pipeline = [OrderStatus.PLACED]
            if status in (OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY_FOR_PICKUP,
                          OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED):
                pipeline.append(OrderStatus.CONFIRMED)
            if status in (OrderStatus.PREPARING, OrderStatus.READY_FOR_PICKUP,
                          OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED):
                pipeline.append(OrderStatus.PREPARING)
            if status in (OrderStatus.READY_FOR_PICKUP, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED):
                pipeline.append(OrderStatus.READY_FOR_PICKUP)

            for step in pipeline:
                order.status_history.create(status=step, note="Seeded demo data", created_at=created)

            if status == OrderStatus.CANCELLED:
                order.status_history.create(status=OrderStatus.CANCELLED, note="Cancelled by customer", created_at=created)
                order.order_status = OrderStatus.CANCELLED
                order.cancellation_reason = "Customer changed their mind"
                order.cancelled_at = created + timedelta(minutes=6)
                order.save(update_fields=["order_status", "cancellation_reason", "cancelled_at"])
                notify(customer, "Order cancelled", f"Order #{order.order_number} was cancelled.",
                       Notification.Kind.ORDER, order.get_absolute_url(), order)
                continue

            if status in (OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED) and riders:
                rider = random.choice(riders)
                assignment = DeliveryAssignment.objects.create(
                    order=order, delivery_boy=rider.user, status=DeliveryAssignment.Status.ASSIGNED,
                    distance_km=Decimal(str(round(random.uniform(1.5, 7.5), 2))),
                    earning_amount=rider.earning_per_delivery,
                )
                DeliveryAssignment.objects.filter(pk=assignment.pk).update(assigned_at=created)
                DeliveryEarning.objects.create(
                    delivery_boy=rider.user, order=order, assignment=assignment,
                    amount=rider.earning_per_delivery,
                    status="SETTLED" if status == OrderStatus.DELIVERED else "PENDING",
                )
                order.delivery_boy = rider.user
                order.status_history.create(status=OrderStatus.ASSIGNED, note="Assigned by admin", created_at=created)
                if status == OrderStatus.OUT_FOR_DELIVERY:
                    order.status_history.create(status=OrderStatus.PICKED_UP, note="Picked up", created_at=created)
                    order.status_history.create(status=OrderStatus.OUT_FOR_DELIVERY, note="Out for delivery", created_at=created)
                    order.order_status = OrderStatus.OUT_FOR_DELIVERY
                    assignment.update_status(DeliveryAssignment.Status.OUT_FOR_DELIVERY)
                if status == OrderStatus.DELIVERED:
                    order.status_history.create(status=OrderStatus.PICKED_UP, note="Picked up", created_at=created)
                    order.status_history.create(status=OrderStatus.OUT_FOR_DELIVERY, note="Out for delivery", created_at=created)
                    order.status_history.create(status=OrderStatus.DELIVERED, note="Delivered", created_at=created)
                    order.order_status = OrderStatus.DELIVERED
                    order.delivered_at = created + timedelta(minutes=restaurant.delivery_time)
                    assignment.update_status(DeliveryAssignment.Status.DELIVERED)
                    # A review from ~70% of delivered orders.
                    if random.random() < 0.75:
                        Review.objects.create(
                            customer=customer, restaurant=restaurant, order=order,
                            rating=random.choice([5, 5, 4, 4, 3]),
                            comment=random.choice([
                                "Food arrived hot and well packed. Will order again!",
                                "Great taste and generous portions. Delivery was quick too.",
                                "Loved the flavours — exactly like eating at the restaurant.",
                                "Good food overall, packaging could be better.",
                                "Delivery took a little longer but the food was worth it.",
                                "",
                            ]),
                        )
            order.save()
            restaurant.recalculate_rating()
