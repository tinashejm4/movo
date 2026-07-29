from django.contrib.auth.models import User

from apps.users.models import Contact, Customer
from apps.users.utils import normalize_zimbabwean_number


LEGACY_CUSTOMER_DEFAULT_PASSWORD = "Pass@123"


def split_customer_name(full_name, fallback_name):
    name = (full_name or fallback_name or "Unknown").strip()
    parts = name.split()
    first_name = parts[0] if parts else "Unknown"
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    return first_name, last_name


def resolve_or_create_customer(phone_number, full_name=None):
    """Return the customer represented by a normalized Zimbabwean phone number.

    The password behavior is intentionally retained during this extraction so
    moving the workflow does not change how counterpart accounts are created.
    It should be replaced by an account-activation flow in a separate change.
    """
    normalized_phone = normalize_zimbabwean_number(phone_number)
    user = User.objects.filter(username=normalized_phone).first()

    if user is None:
        first_name, last_name = split_customer_name(full_name, normalized_phone)
        user = User.objects.create_user(
            username=normalized_phone,
            password=LEGACY_CUSTOMER_DEFAULT_PASSWORD,
            first_name=first_name.capitalize(),
            last_name=last_name.capitalize(),
        )

    Contact.objects.get_or_create(
        user=user,
        defaults={"phone_number": normalized_phone},
    )
    customer, _ = Customer.objects.get_or_create(user=user)
    return customer
