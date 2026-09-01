from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.intracity.models import Package, PackageStatus


@transaction.atomic
def free_drivers_and_close_packages():
    """Close every assigned package and remove its biker assignment.

    In-transit packages are treated as delivered. Packages at any other
    non-terminal stage are cancelled. Existing terminal statuses are kept.
    This intentionally destructive helper is isolated for easy removal after
    driver-app testing.
    """
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

    return {
        "message": "Drivers freed and assigned packages closed",
        "freed_driver_assignments": len(packages),
        "delivered_packages": delivered_count,
        "cancelled_packages": cancelled_count,
    }
