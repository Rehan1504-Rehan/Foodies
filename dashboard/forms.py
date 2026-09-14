"""Forms for restaurant management, menu management and offers."""

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from accounts.forms import validate_image_size
from delivery.models import DeliveryBoyProfile
from menu.models import Category, FoodItem
from offers.models import Coupon
from restaurants.models import Restaurant

User = get_user_model()


class BootstrapFormMixin:
    """Apply Bootstrap classes to every widget so templates stay clean."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")
            if isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.Textarea)):
                widget.attrs.setdefault("autocomplete", "off")


class RestaurantForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Restaurant
        fields = [
            "name", "description", "phone", "email", "address", "area", "city", "state",
            "pincode", "cuisine_type", "delivery_time", "delivery_fee", "minimum_order",
            "is_open", "logo", "cover_image",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Tell customers what makes your kitchen special"}),
            "cuisine_type": forms.TextInput(attrs={"placeholder": "North Indian, Chinese, Desserts"}),
            "logo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "cover_image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean_logo(self):
        return validate_image_size(self.cleaned_data.get("logo"))

    def clean_cover_image(self):
        return validate_image_size(self.cleaned_data.get("cover_image"))

    def clean_pincode(self):
        pincode = (self.cleaned_data.get("pincode") or "").strip()
        if pincode and (not pincode.isdigit() or len(pincode) != 6):
            raise ValidationError("Enter a valid 6 digit pincode.")
        return pincode

    def clean_minimum_order(self):
        value = self.cleaned_data.get("minimum_order")
        if value is not None and value < 0:
            raise ValidationError("Minimum order cannot be negative.")
        return value

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("cuisine_type"):
            raise ValidationError({"cuisine_type": "Add at least one cuisine type."})
        return cleaned


class CategoryForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description", "icon", "image", "display_order", "is_active"]
        widgets = {
            "icon": forms.TextInput(attrs={"placeholder": "🍕", "maxlength": 4}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean_image(self):
        return validate_image_size(self.cleaned_data.get("image"))


class FoodItemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = FoodItem
        fields = [
            "category", "name", "description", "price", "discount_price", "image",
            "is_veg", "is_available", "is_recommended", "preparation_time",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "Short, appetising description"}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "preparation_time": forms.NumberInput(attrs={"min": 1, "max": 180}),
        }

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.restaurant = restaurant or getattr(self.instance, "restaurant", None)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Select a category"

    def clean_image(self):
        return validate_image_size(self.cleaned_data.get("image"))

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get("price")
        discount_price = cleaned.get("discount_price")
        if price is not None and price <= 0:
            raise ValidationError({"price": "Price must be greater than zero."})
        if discount_price is not None and price is not None and discount_price >= price:
            raise ValidationError({"discount_price": "Discount price must be lower than the base price."})
        return cleaned

    def save(self, commit=True):
        item = super().save(commit=False)
        if self.restaurant is not None and item.restaurant_id is None:
            item.restaurant = self.restaurant
        if commit:
            item.save()
        return item


class CouponForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code", "title", "description", "discount_type", "discount_value", "minimum_order",
            "maximum_discount", "valid_from", "valid_until", "usage_limit", "per_user_limit",
            "restaurant", "first_order_only", "is_active",
        ]
        widgets = {
            "valid_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "valid_until": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, restaurant=None, **kwargs):
        self.restaurant = restaurant
        super().__init__(*args, **kwargs)
        if restaurant is not None:
            # Restaurant owners may only create coupons for their own kitchen.
            self.fields["restaurant"].queryset = Restaurant.objects.filter(pk=restaurant.pk)
            self.fields["restaurant"].initial = restaurant
            self.fields["restaurant"].disabled = True

    def clean_code(self):
        code = (self.cleaned_data["code"] or "").upper().strip()
        if not code.isalnum():
            raise ValidationError("Coupon codes may only contain letters and numbers.")
        return code

    def clean(self):
        cleaned = super().clean()
        valid_from, valid_until = cleaned.get("valid_from"), cleaned.get("valid_until")
        if valid_from and valid_until and valid_until <= valid_from:
            raise ValidationError({"valid_until": "Valid-until must be after valid-from."})
        if cleaned.get("discount_type") == Coupon.DiscountType.PERCENT and (cleaned.get("discount_value") or 0) > 100:
            raise ValidationError({"discount_value": "Percentage discount cannot exceed 100%."})
        return cleaned


class DeliveryBoyForm(BootstrapFormMixin, forms.Form):
    """Admin form used to onboard a delivery partner."""

    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80, required=False)
    email = forms.EmailField()
    phone = forms.RegexField(r"^[0-9+\-\s]{10,15}$", error_messages={"invalid": "Enter a valid phone number."})
    password = forms.CharField(min_length=8, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    vehicle_type = forms.ChoiceField(choices=DeliveryBoyProfile.VehicleType.choices)
    vehicle_number = forms.CharField(max_length=20, required=False)
    license_number = forms.CharField(max_length=30, required=False)
    current_area = forms.CharField(max_length=120, required=False)
    is_approved = forms.BooleanField(required=False, initial=True, label="Approve immediately")

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email
