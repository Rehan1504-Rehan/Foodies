"""Provision the canonical FOODIES admin account.

The operator-facing login accepts the user ID ADMIN and maps it to this
canonical email-based account.  The password is hashed by Django immediately;
it is never stored in plaintext in the database.
"""

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


ADMIN_EMAIL = "admin@foodies.test"
ADMIN_PASSWORD = getattr(settings, "ADMIN_LOGIN_PASSWORD", "Password@123")


def provision_admin(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    user, _ = User.objects.get_or_create(
        email=ADMIN_EMAIL,
        defaults={
            "first_name": "Admin",
            "last_name": "User",
            "phone": "9000000000",
            "role": "ADMIN",
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
            "email_verified": True,
        },
    )
    user.first_name = "Admin"
    user.last_name = "User"
    user.phone = user.phone or "9000000000"
    user.role = "ADMIN"
    user.is_active = True
    user.is_staff = True
    user.is_superuser = True
    user.email_verified = True
    user.password = make_password(ADMIN_PASSWORD)
    user.save()


def keep_admin_account(apps, schema_editor):
    """Do not remove an operator account during a migration rollback."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(provision_admin, keep_admin_account),
    ]
