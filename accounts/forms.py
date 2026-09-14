"""Authentication, profile and address forms for FOODIES."""

from django import forms
from django.conf import settings
from django.contrib.admin.forms import (
    AdminAuthenticationForm as DjangoAdminAuthenticationForm,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import Address

User = get_user_model()


def validate_image_size(uploaded_file, max_mb=4):
    """Reject oversized / non-image uploads before they reach storage."""
    if not uploaded_file:
        return uploaded_file
    if hasattr(uploaded_file, "size") and uploaded_file.size > max_mb * 1024 * 1024:
        raise ValidationError(f"Image must be smaller than {max_mb} MB.")
    name = getattr(uploaded_file, "name", "").lower()
    allowed = (".jpg", ".jpeg", ".png", ".webp", ".gif")
    if not name.endswith(allowed):
        raise ValidationError("Only JPG, PNG, WEBP or GIF images are allowed.")
    return uploaded_file


class FoodieAuthenticationForm(AuthenticationForm):
    """Login with e-mail + password, FOODIES styling and friendly errors."""

    username = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={"class": "form-control form-control-lg", "placeholder": "you@example.com", "autofocus": True}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"class": "form-control form-control-lg", "placeholder": "••••••••"}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Incorrect email or password. Please try again.",
    }


class AdminAuthenticationForm(DjangoAdminAuthenticationForm):
    """Django's stock admin login form, extended with the ``ADMIN`` user ID.

    The FOODIES user model signs in with e-mail addresses, so the canonical
    admin account lives at ``admin@foodies.test``.  Operators are used to the
    simpler user ID ``ADMIN`` though — translate it to that e-mail before
    Django's regular authentication runs.  Everything else stays standard:
    the built-in admin URLs and templates, and the normal staff permission
    checks in ``confirm_login_allowed()``.
    """

    error_messages = {
        **DjangoAdminAuthenticationForm.error_messages,
        # Keep the stock admin wording, but with the "Username" label shown on
        # the FOODIES login instead of the model's e-mail field name.
        "invalid_login": (
            "Please enter the correct username and password for a staff "
            "account. Note that both fields may be case-sensitive."
        ),
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        # The model-level login identifier is the e-mail address; the admin
        # screen keeps its familiar "Username" label.
        self.fields["username"].label = "Username"

    def clean(self):
        username = (self.cleaned_data.get("username") or "").strip()
        admin_id = getattr(settings, "ADMIN_LOGIN_ID", "ADMIN")
        if username and username.casefold() == admin_id.casefold():
            # ADMIN is an alias for the canonical admin e-mail; the address
            # itself keeps working for operators who used it before.
            self.cleaned_data["username"] = getattr(settings, "ADMIN_LOGIN_EMAIL", "admin@foodies.test")
        return super().clean()


class BaseRegisterForm(UserCreationForm):
    """Shared registration fields; the role is supplied by the subclasses."""

    first_name = forms.CharField(max_length=80, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Rahul"}))
    last_name = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Sharma"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}))
    phone = forms.RegexField(
        r"^[0-9+\-\s]{10,15}$",
        error_messages={"invalid": "Enter a valid phone number."},
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "9876543210"}),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget = forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "At least 8 characters", "autocomplete": "new-password"}
        )
        self.fields["password2"].widget = forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Repeat password", "autocomplete": "new-password"}
        )

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists. Try logging in instead.")
        return email

    def clean_phone(self):
        return self.cleaned_data["phone"].strip()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data.get("last_name", "")
        user.phone = self.cleaned_data["phone"]
        if commit:
            user.save()
        return user


class CustomerRegisterForm(BaseRegisterForm):
    class Meta(BaseRegisterForm.Meta):
        fields = ["first_name", "last_name", "email", "phone"]


class RestaurantOwnerRegisterForm(BaseRegisterForm):
    restaurant_name = forms.CharField(
        max_length=120, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Spice Route Kitchen"})
    )
    city = forms.CharField(max_length=80, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ahmedabad"}))

    class Meta(BaseRegisterForm.Meta):
        fields = ["first_name", "last_name", "email", "phone", "restaurant_name", "city"]


class DeliveryRegisterForm(BaseRegisterForm):
    vehicle_type = forms.ChoiceField(
        choices=[("BIKE", "Bike"), ("SCOOTER", "Scooter"), ("BICYCLE", "Bicycle"), ("EV", "Electric Vehicle")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    vehicle_number = forms.CharField(max_length=20, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "GJ01AB1234"}))
    license_number = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "DL-1234567890"}))

    class Meta(BaseRegisterForm.Meta):
        fields = ["first_name", "last_name", "email", "phone", "vehicle_type", "vehicle_number", "license_number"]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "profile_image"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "profile_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
        }

    def clean_profile_image(self):
        return validate_image_size(self.cleaned_data.get("profile_image"))


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            "full_name", "phone", "address_line", "area", "city", "state",
            "pincode", "landmark", "address_type", "label", "latitude", "longitude", "is_default",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Rahul Sharma"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "9876543210"}),
            "address_line": forms.TextInput(attrs={"class": "form-control", "placeholder": "Flat / House no, Building, Street"}),
            "area": forms.TextInput(attrs={"class": "form-control", "placeholder": "Satellite"}),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ahmedabad"}),
            "state": forms.TextInput(attrs={"class": "form-control", "placeholder": "Gujarat"}),
            "pincode": forms.TextInput(attrs={"class": "form-control", "placeholder": "380015"}),
            "landmark": forms.TextInput(attrs={"class": "form-control", "placeholder": "Near Shivranjani Cross Road"}),
            "address_type": forms.Select(attrs={"class": "form-select"}),
            "label": forms.TextInput(attrs={"class": "form-control", "placeholder": "Home / Hostel / Parents"}),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
            "is_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_pincode(self):
        pincode = (self.cleaned_data.get("pincode") or "").strip()
        if not pincode.isdigit() or len(pincode) != 6:
            raise ValidationError("Enter a valid 6 digit pincode.")
        return pincode

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if len(phone) < 10:
            raise ValidationError("Enter a valid phone number.")
        return phone
