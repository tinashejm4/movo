import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.users.models import Biker, Contact,ProfileImage

from ..models import Package, PackageStatus



logger = logging.getLogger(__name__)


def is_biker_busy(biker):
    """Return whether a biker has a package awaiting collection or in transit."""
    latest_status = (
        PackageStatus.objects.filter(package=OuterRef("pk"))
        .order_by("-updated_at", "-pk")
        .values("status")[:1]
    )
    return (
        Package.objects.filter(biker=biker, added_at__date=timezone.now().date())
        .annotate(current_status=Subquery(latest_status))
        .filter(current_status__in=["Assigned", "In Transit"])
        .exists()
    )


def assign_pending_packages():
    """Assign available bikers to today's pending packages.

    Biker rows are locked in a stable order so concurrent dispatch attempts
    cannot assign the same biker to multiple active packages.
    """
    with transaction.atomic():
        latest_status = (
            PackageStatus.objects.filter(package=OuterRef("pk"))
            .order_by("-updated_at", "-pk")
            .values("status")[:1]
        )

        logger.info(latest_status)

        # Lock all bikers first to serialize concurrent assignment runs.
        bikers = list(
            Biker.objects.select_for_update()
            .select_related("user")
            .order_by("id")
        )

        pending_packages = list(
            Package.objects.select_for_update()
            .filter(added_at__date=timezone.now().date())
            .annotate(status=Subquery(latest_status))
            .filter(status="Pending")
            .order_by("-is_fast_delivery", "added_at")
        )

        if not pending_packages:
            logger.info("assign_pending_packages: no pending packages found")
            return _result("No pending packages available for assignment")

        free_bikers = [biker for biker in bikers if not is_biker_busy(biker)]

        if not free_bikers:
            logger.info("assign_pending_packages: no available bikers")
            return _result(
                "No available bikers for assignment",
                unassigned_count=len(pending_packages),
            )

        assigned_packages = []
        assigned_at = timezone.now()
        for package, biker in zip(pending_packages, free_bikers):
            package.biker = biker
            package.assigned_at = assigned_at
            package.save(update_fields=["biker", "assigned_at"])
            PackageStatus.objects.create(package=package, status="Assigned")
            assigned_packages.append(_assignment_payload(package, biker))

        unassigned_count = max(
            len(pending_packages) - len(assigned_packages),
            0,
        )
        transaction.on_commit(
            lambda payloads=tuple(assigned_packages): _publish_assignments(
                payloads
            )
        )

        return _result(
            "Pending packages assigned successfully",
            assigned_packages=assigned_packages,
            unassigned_count=unassigned_count,
        )


def assign_pending_packages_safely():
    """Run automatic dispatch without breaking the package-creation response."""
    try:
        return assign_pending_packages()
    except Exception:
        logger.exception("Automatic package assignment failed")
        return _result("Automatic package assignment failed")


def _assignment_payload(package, biker):
    contact = Contact.objects.filter(user=biker.user).first()
    profile_picture = ProfileImage.objects.filter(user=biker.user).first()
    return {
        "package_id": package.id,
        "slug": package.slug,
        "biker_id": biker.id,
        "biker_name": (
            f"{biker.user.first_name} {biker.user.last_name}".strip()
        ),
        "biker_phone_number": contact.phone_number if contact else None,
        "biker_profile_pic": profile_picture.profile_image.url if profile_picture and profile_picture.profile_image else None,
        "package_pickup_area": package.pickup_area.name if hasattr(package, "pickup_area") else None,
        "package_pickup_address": package.pickup_address                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            if hasattr(package, "pickup_address") else None,
        "sender_name": f"{package.sender.user.first_name} {package.sender.user.last_name}",
        "sender_phone": f"+263{package.sender.user.username}",
        "receiver_name": f"{package.receiver.user.first_name} {package.receiver.user.last_name}",
        "receiver_phone": f"+263{package.receiver.user.username}",
        "comments": package.comments if hasattr(package, "comments") else None,

        "assigned_at": (
            package.assigned_at.isoformat() if package.assigned_at else None
        ),
        "added_at": package.added_at.isoformat() if package.added_at else None,
    }


def _publish_assignments(assignments):
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("WebSocket publish skipped: no channel layer configured")
        return

    for payload in assignments:
        try:
            logger.info(
                "assign_pending_packages: publishing package_id=%s biker_id=%s",
                payload["package_id"],
                payload["biker_id"],
            )
            async_to_sync(channel_layer.group_send)(
                "package_assignments",
                {"type": "package.assigned", "payload": payload},
            )
            async_to_sync(channel_layer.group_send)(
                f"package_{payload['package_id']}",
                {"type": "package.assigned", "payload": payload},
            )
            async_to_sync(channel_layer.group_send)(
                f"biker_orders_{payload['biker_id']}",
                {"type": "order.assigned", "payload": payload},
            )
        except Exception:
            logger.exception(
                "WebSocket assignment publish failed for package_id=%s",
                payload["package_id"],
            )


def _result(
    message,
    *,
    assigned_packages=None,
    unassigned_count=0,
):
    assignments = assigned_packages or []
    return {
        "message": message,
        "assigned_count": len(assignments),
        "unassigned_count": unassigned_count,
        "assigned_packages": assignments,
    }
