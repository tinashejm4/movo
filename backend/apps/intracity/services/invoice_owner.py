from .package_access import package_payer


def invoice_order(invoice):
    return getattr(invoice, "package", None) or getattr(invoice, "round_trip", None)


def invoice_payer(invoice):
    package = getattr(invoice, "package", None)
    if package is not None:
        return package_payer(package, invoice)
    return invoice.round_trip.sender


def invoice_participant_user_ids(invoice):
    return order_participant_user_ids(invoice_order(invoice))


def order_participant_user_ids(order):
    receiver = order.receiver if hasattr(order, "receiver") else order.recipient
    return {order.sender.user_id, receiver.user_id,
            order.biker.user_id if order.biker_id else None}


def invoice_is_cancelled(invoice):
    if invoice.round_trip_id:
        return invoice.round_trip.status == "Cancelled"
    from .invoice_payment import package_is_cancelled
    return package_is_cancelled(invoice.package)


def ensure_invoice_refund_review(invoice):
    if invoice.package_id:
        from .package_expiration import ensure_refund_review
        return ensure_refund_review(invoice.package)
    if not invoice.is_paid or invoice.round_trip.status != "Cancelled":
        return None
    from ..models import RefundReview
    review, _ = RefundReview.objects.get_or_create(
        invoice=invoice,
        defaults={"recipient": invoice.round_trip.sender, "amount": invoice.amount,
                  "payment_method": invoice.payment_method or ""},
    )
    return review


def lock_invoice_order(invoice_id):
    from ..models import Invoice, Package, RoundTripOrder
    owner_ids = Invoice.objects.filter(pk=invoice_id).values("package_id", "round_trip_id").first()
    if owner_ids is None:
        return
    if owner_ids["package_id"]:
        Package.objects.select_for_update().get(pk=owner_ids["package_id"])
    else:
        RoundTripOrder.objects.select_for_update().get(pk=owner_ids["round_trip_id"])
