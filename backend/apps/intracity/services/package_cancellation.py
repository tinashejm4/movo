"""Shared package cancellation policy."""


CANCELLABLE_PACKAGE_STATUS = "Pending"


def can_cancel_package(*, invoice, current_status):
    """Return whether the package is currently eligible for cancellation."""
    is_paid = bool(invoice and invoice.is_paid)
    return current_status == CANCELLABLE_PACKAGE_STATUS and not is_paid
