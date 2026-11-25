from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from ..models import EcocashPayment, PackageStatus, PaynowPayment
from .invoice_owner import invoice_order, invoice_payer, invoice_is_cancelled


PAYMENT_ATTEMPT_PENDING_WINDOW = timedelta(minutes=2)


def invoice_user_is_payer(invoice, user_id):
    if invoice is None or user_id is None:
        return False

    try:
        return user_id == invoice_payer(invoice).user_id
    except (AttributeError, TypeError):
        return False


def invoice_user_is_assigned_biker(invoice, user_id):
    """Whether this user is the biker currently assigned to the invoice package."""
    if invoice is None or user_id is None:
        return False

    try:
        return (
            invoice_order(invoice).biker is not None
            and invoice_order(invoice).biker.user_id == user_id
        )
    except (AttributeError, TypeError):
        return False


def invoice_user_can_start_payment(invoice, user_id):
    """Allow the payer or assigned biker to initiate a payment request."""
    if not (
        invoice_user_is_payer(invoice, user_id)
        or invoice_user_is_assigned_biker(invoice, user_id)
    ):
        return False
    if invoice.is_paid or invoice_is_cancelled(invoice):
        return False

    try:
        return Decimal(invoice.amount) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def invoice_has_pending_payment(invoice):
    if invoice is None:
        return False

    unresolved_attempt = {
        "invoice": invoice,
        "is_successful": False,
        "paid_at__isnull": True,
        "created_at__gte": timezone.now() - PAYMENT_ATTEMPT_PENDING_WINDOW,
    }
    return (
        EcocashPayment.objects.filter(**unresolved_attempt).exists()
        or PaynowPayment.objects.filter(**unresolved_attempt).exists()
    )


def package_is_cancelled(package):
    if package is None:
        return True

    latest_status = (
        PackageStatus.objects.filter(package=package)
        .order_by("-updated_at", "-pk")
        .values_list("status", flat=True)
        .first()
    )
    return latest_status in {"Cancelled", "Expired"}


def invoice_user_can_pay(invoice, user_id):
    if not invoice_user_is_payer(invoice, user_id):
        return False
    if invoice.is_paid or invoice_is_cancelled(invoice):
        return False

    try:
        if Decimal(invoice.amount) <= 0:
            return False
    except (InvalidOperation, TypeError, ValueError):
        return False

    return True
