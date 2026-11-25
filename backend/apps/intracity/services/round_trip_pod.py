import hashlib

from django.db import transaction

from ..models import RoundTripAssignment, RoundTripOrder, RoundTripPOD, RoundTripStop


@transaction.atomic
def upload_round_trip_pod(*, order_id, stop_id, user, data):
    order = RoundTripOrder.objects.select_for_update().filter(pk=order_id).first()
    if not order:
        return None, "Order not found", 404
    assignment = RoundTripAssignment.objects.filter(
        pk=data["assignment_id"], order=order, biker=order.biker,
        biker__user=user,
    ).first()
    if not assignment:
        return None, "Active assignment required", 403
    stop = RoundTripStop.objects.select_for_update().filter(
        pk=stop_id, order=order, kind="recipient",
    ).first()
    if not stop:
        return None, "Recipient stop not found", 404
    image = data["image"]
    digest = hashlib.sha256()
    for chunk in image.chunks():
        digest.update(chunk)
    image.seek(0)
    checksum = digest.hexdigest()
    existing = RoundTripPOD.objects.filter(upload_id=data["upload_id"]).first()
    if existing:
        if (existing.stop_id != stop.pk or existing.assignment_id != assignment.pk
                or existing.sha256 != checksum or existing.uploaded_by_id != user.pk):
            return None, "upload_id reused with different data", 409
        return existing, None, 200
    if assignment.ended_at is not None:
        return None, "Active assignment required", 403
    if order.status not in {"Assigned", "In Transit"}:
        return None, "Order is not accepting POD", 409
    active_stop = order.stops.filter(completed_at__isnull=True).order_by("sequence").first()
    if not active_stop or active_stop.pk != stop.pk:
        return None, "Recipient stop is not active", 409
    if RoundTripPOD.objects.filter(stop=stop).exists():
        return None, "POD already uploaded for this stop", 409
    pod = RoundTripPOD.objects.create(
        stop=stop, assignment=assignment, image=image, upload_id=data["upload_id"],
        sha256=checksum, uploaded_by=user,
    )
    return pod, None, 201
