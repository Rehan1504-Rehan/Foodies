"""Custom user model + manager for FOODIES.

Authentication is email based and every account carries a role which drives the
entire role-based access-control layer of the platform.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Manager for the email-based ``User`` model."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password", "last_login"])
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", User.Role.CUSTOMER)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("email_verified", True)
        if not extra_fields.get("is_staff") or not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_staff and is_superuser set to True.")
        return self._create_user(email, password, **extra_fields)

    def customers(self):
        return self.filter(role=User.Role.CUSTOMER)

    def restaurant_owners(self):
        return self.filter(role=User.Role.RESTAURANT_OWNER)

    def delivery_boys(self):
        return self.filter(role=User.Role.DELIVERY_BOY)


class User(AbstractBaseUser, PermissionsMixin):
    """Single user table for all four FOODIES roles."""

    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        RESTAURANT_OWNER = "RESTAURANT_OWNER", "Restaurant Owner"
        DELIVERY_BOY = "DELIVERY_BOY", "Delivery Boy"
        ADMIN = "ADMIN", "Admin"

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=15, blank=True, db_index=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    profile_image = models.ImageField(upload_to="profiles/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    blocked_reason = models.CharField(max_length=255, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        ordering = ["-date_joined"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower().strip()
        self.is_staff = self.is_staff or self.role == self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.email.split("@")[0]

    @property
    def short_name(self):
        return self.first_name or self.email.split("@")[0]

    @property
    def initials(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        if not parts:
            return self.email[:1].upper()
        return "".join(p[0].upper() for p in parts[:2])

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_restaurant_owner(self):
        return self.role == self.Role.RESTAURANT_OWNER

    @property
    def is_delivery_boy(self):
        return self.role == self.Role.DELIVERY_BOY

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def get_full_name(self):
        return self.full_name


class Address(models.Model):
    """A saved delivery address belonging to a customer."""

    class AddressType(models.TextChoices):
        HOME = "HOME", "Home"
        WORK = "WORK", "Work"
        OTHER = "OTHER", "Other"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=60, blank=True)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    address_line = models.CharField(max_length=255)
    area = models.CharField(max_length=120)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=10)
    landmark = models.CharField(max_length=150, blank=True)
    address_type = models.CharField(max_length=10, choices=AddressType.choices, default=AddressType.HOME)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        verbose_name_plural = "Addresses"

    def __str__(self):
        return f"{self.full_name}, {self.area}, {self.city} ({self.pincode})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Address.objects.filter(user=self.user).exclude(pk=self.pk).update(is_default=False)
        elif not Address.objects.filter(user=self.user, is_default=True).exists():
            Address.objects.filter(pk=self.pk).update(is_default=True)
            self.is_default = True

    @property
    def one_line(self):
        parts = [self.address_line, self.area, self.city, self.state, self.pincode]
        return ", ".join(p for p in parts if p)

    @property
    def short_line(self):
        return f"{self.area}, {self.city} - {self.pincode}"

    @property
    def full_address(self):
        if self.landmark:
            return f"{self.one_line} (Landmark: {self.landmark})"
        return self.one_line
