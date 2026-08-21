from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from ..models import EcocashPayment, PackageStatus, PaynowPayment
from .package_access import package_payer_user_id


PAYMENT_ATTEMPT_PENDING_WINDOW = timedelta(minutes=2)


def invoice_user_is_payer(invoice, user_id):
    if invoice is None or user_id is None:
        return False

    try:
        package = invoice.package
        participant_user_ids = {
            package.sender.user_id,
            package.receiver.user_id,
        }
        if user_id not in participant_user_ids:
            return False
        return user_id == package_payer_user_id(package, invoice)
    except (AttributeError, TypeError):
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
    return latest_status == "Cancelled"


def invoice_user_can_pay(invoice, user_id):
    if not invoice_user_is_payer(invoice, user_id):
        return False
    if invoice.is_paid or package_is_cancelled(invoice.package):
        return False

    try:
        if Decimal(invoice.amount) <= 0:
            return False
    except (InvalidOperation, TypeError, ValueError):
        return False

    return True
