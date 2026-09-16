import logging

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.bookkeeping.models import Account, IntracitySale
from apps.intracity.models import Invoice, Package, PackageStatus
from logging import getLogger
logger = getLogger(__name__)

class CashConfirmationError(Exception):
    status_code = 400


class CashConfirmationNotFound(CashConfirmationError):
    status_code = 404


class CashConfirmationForbidden(CashConfirmationError):
    status_code = 403


@transaction.atomic
def confirm_cash_received(*, package_id, biker_user):
    """Record a driver's confirmation that the invoice amount was received.

    The invoice amount is the only amount recorded; it is never accepted from
    the client.  Locking the package and invoice makes retries idempotent and
    prevents duplicate cash ledger entries.
    """
    package = (
        Package.objects.select_for_update()
        .filter(pk=package_id)
        .first()
    )
    if not package:
        raise CashConfirmationNotFound("Package not found")
    if not package.biker or package.biker.user_id != biker_user.id:
        raise CashConfirmationForbidden("You are not assigned to this package")

    invoice = Invoice.objects.select_for_update().filter(package=package).first()
    if not invoice:
        raise CashConfirmationError("Package cannot be paid because the invoice is missing")

    sale = IntracitySale.objects.filter(invoice=invoice).first()
    if invoice.is_paid and invoice.payment_method != "Cash":
        raise CashConfirmationError("Invoice has already been paid electronically")
    if invoice.is_paid and invoice.payment_method == "Cash" and sale:
        return {
            "invoice_id": invoice.id,
            "package_id": package.id,
            "amount": invoice.amount,
            "paid_at": invoice.paid_at,
            "sale_id": sale.id,
        }

    latest_status = (
        PackageStatus.objects.select_for_update()
        .filter(package=package)
        .order_by("-updated_at", "-pk")
        .first()
    )
    required_statuses = {"In Transit"} if invoice.is_pay_forward else {"Pending", "Assigned"}
    required_status_label = (
        "In Transit" if invoice.is_pay_forward else "Pending or Assigned"
    )
    if not latest_status or latest_status.status not in required_statuses:
        raise CashConfirmationError(
            f"Cash can only be confirmed when the package is {required_status_label}"
        )

    if not sale:
        account = Account.objects.filter(owner=biker_user).first()
        if not account:
            raise CashConfirmationError("Driver cash account not found")
        sale = IntracitySale.objects.create(
            account=account,
            invoice=invoice,
            amount=float(invoice.amount),
        )

    if not invoice.is_paid or invoice.payment_method != "Cash":
        invoice.payment_method = "Cash"
        invoice.exchange_rate = None
        invoice.is_paid = True
        invoice.paid_at = timezone.now()
        invoice.save(
            update_fields=["payment_method", "exchange_rate", "is_paid", "paid_at"]
        )

    return {
        "invoice_id": invoice.id,
        "package_id": package.id,
        "amount": invoice.amount,
        "paid_at": invoice.paid_at,
        "sale_id": sale.id,
    }


@transaction.atomic
def free_drivers_and_close_packages():
    """Close every assigned package and remove its biker assignment.

    In-transit packages are treated as delivered. Packages at any other
    non-terminal stage are cancelled. Existing terminal statuses are kept.
    This intentionally destructive helper is isolated for easy removal after
    driver-app testing.
    """
    logger.log(logging.INFO, "Starting free_drivers_and_close_packages operation")
    latest_status = (
        PackageStatus.objects.filter(package=OuterRef("pk"))
        .order_by("-updated_at", "-pk")
        .values("status")[:1]
    )
    packages = list(
        Package.objects.select_for_update()
        .filter(biker__isnull=False)
        .annotate(current_status=Subquery(latest_status))
        .order_by("pk")
    )

    now = timezone.now()
    delivered_count = 0
    cancelled_count = 0
    statuses = []

    for package in packages:
        if package.current_status == "In Transit":
            statuses.append(
                PackageStatus(package=package, status="Delivered")
            )
            package.delivered_at = now
            delivered_count += 1
        elif package.current_status not in {"Delivered", "Cancelled"}:
            statuses.append(
                PackageStatus(
                    package=package,
                    status="Cancelled",
                    comments="Closed by driver-app test reset",
                )
            )
            cancelled_count += 1

        package.biker = None
        package.assigned_at = None

    if statuses:
        PackageStatus.objects.bulk_create(statuses)
    if packages:
        Package.objects.bulk_update(
            packages,
            ["biker", "assigned_at", "delivered_at"],
        )

    result = {
        "message": "Drivers freed and assigned packages closed",
        "freed_driver_assignments": len(packages),
        "delivered_packages": delivered_count,
        "cancelled_packages": cancelled_count,
    }
    logger.log(logging.INFO, f"Finished free_drivers_and_close_packages operation: {result}")
    return result
