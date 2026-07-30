import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.users.models import Biker

from ..models import Package, PackageStatus


logger = logging.getLogger(__name__)


def assign_pending_packages():
    """Assign available bikers to today's pending packages.

    Biker rows are locked in a stable order so concurrent dispatch attempts
    cannot assign the same biker to multiple active packages.
    """
    with transaction.atomic():
        latest_status = (
            PackageStatus.objects.filter(package=OuterRef("pk"))
            .order_by("-updated_at")
            .values("status")[:1]
        )

        # Lock all bikers first to serialize concurrent assignment runs.
        bikers = list(
            Biker.objects.select_for_update()
            .select_related("user")
            .order_by("id")
        )

        pending_packages = list(
            Package.objects.select_for_update()
            .filter(biker__isnull=True, added_at__date=timezone.now().date())
            .annotate(current_status=Subquery(latest_status))
            .filter(current_status="Pending")
            .order_by("-is_fast_delivery", "added_at")
        )

        if not pending_packages:
            logger.info("assign_pending_packages: no pending packages found")
            return _result("No pending packages available for assignment")

        active_biker_ids = set(
            Package.objects.filter(biker__isnull=False)
            .annotate(current_status=Subquery(latest_status))
            .filter(current_status__in=["Pending", "In Transit"])
            .values_list("biker_id", flat=True)
        )
        free_bikers = [biker for biker in bikers if biker.id not in active_biker_ids]

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

        logger.info(
            "assign_pending_packages: assigned_count=%s unassigned_count=%s",
            len(assigned_packages),
            unassigned_count,
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
    return {
        "package_id": package.id,
        "slug": package.slug,
        "is_fast_delivery": package.is_fast_delivery,
        "biker_id": biker.id,
        "biker_name": (
            f"{biker.user.first_name} {biker.user.last_name}".strip()
        ),
        "biker_phone": f"0{biker.user.username}",
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
