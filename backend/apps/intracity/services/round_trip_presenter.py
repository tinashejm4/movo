from django.urls import reverse


def stop_payload(stop):
    return {
        "id": stop.pk,
        "sequence": stop.sequence,
        "kind": stop.kind,
        "area_id": stop.area_id,
        "address": stop.address,
        "contact_name": f"{stop.contact.user.first_name} {stop.contact.user.last_name}".strip(),
        "completed_at": stop.completed_at,
        "actions": [
            {"type": action.action, "completed_at": action.completed_at}
            for action in stop.actions.all()
        ],
        "has_pod": hasattr(stop, "pod"),
        "pod_url": (
            reverse("intracity_round_trip_pod", kwargs={"pk": stop.order_id, "stop_id": stop.pk})
            if hasattr(stop, "pod") and stop.completed_at else None
        ),
    }


def order_payload(order, *, detail=False):
    stops = list(order.stops.all())
    active_stop = next((stop for stop in stops if stop.completed_at is None), None)
    payload = {
        "round_trip_id": order.pk,
        "slug": order.slug,
        "status": order.status,
        "parcel_description": order.parcel.description,
        "created_at": order.created_at,
        "driver_id": order.biker_id,
        "active_stop": stop_payload(active_stop) if active_stop and order.status not in {"Cancelled", "Completed"} else None,
    }
    if detail:
        cash = list(order.cash_events.all())
        payload.update({
            "sender_id": order.sender_id,
            "recipient_id": order.recipient_id,
            "city_id": order.city_id,
            "cash_amount": order.cash_amount,
            "cash_currency": order.cash_currency,
            "cash_collected": sum((e.amount for e in cash if e.kind == "collected"), 0),
            "cash_returned": sum((e.amount for e in cash if e.kind == "returned"), 0),
            "invoice_id": order.invoice.pk,
            "delivery_fee": order.invoice.amount,
            "assigned_at": order.assigned_at,
            "completed_at": order.completed_at,
            "exception_reason": order.exception_reason,
            "stops": [stop_payload(stop) for stop in stops],
        })
    return payload
