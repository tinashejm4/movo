from datetime import date, datetime, time, timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Case, IntegerField, OuterRef, Subquery, Value, When
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response

from apps.intracity.models import Package, PackageStatus
from apps.users.permissions import IsStaff


def _parse_metrics_date(value, field_name):
    if value is None:
        return timezone.localdate()
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an ISO date in YYYY-MM-DD format")


def _date_range(start_date, end_date):
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    return start, end


def _metric_series(events, start_date, end_date, bucket_days, unique_key_index=None):
    bucket_starts = []
    current_date = start_date
    while current_date <= end_date:
        bucket_starts.append(current_date)
        current_date += timedelta(days=bucket_days)

    values = [0] * len(bucket_starts)
    seen = set()
    for event in events:
        event_date = event[0] if isinstance(event, tuple) else event
        event_date = timezone.localtime(event_date).date()
        bucket_index = (event_date - start_date).days // bucket_days
        if 0 <= bucket_index < len(values):
            if unique_key_index is not None:
                unique_key = (bucket_index, event[unique_key_index])
                if unique_key in seen:
                    continue
                seen.add(unique_key)
            values[bucket_index] += 1

    return [
        {"date": bucket_date.isoformat(), "value": value}
        for bucket_date, value in zip(bucket_starts, values)
    ]


class DeliveryPageView(ViewSet):
    permission_classes = [IsAuthenticated, IsStaff]

    class DeliveryListPagination(PageNumberPagination):
        page_size = 10
        page_size_query_param = "page_size"
        max_page_size = 100

    def delivery_metrics(self, request):
        try:
            start_date = _parse_metrics_date(
                request.query_params.get("start_date"), "start_date"
            )
            end_date = _parse_metrics_date(
                request.query_params.get("end_date"), "end_date"
            )
        except ValueError as error:
            return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        if start_date > end_date:
            return Response(
                {"error": "start_date must be on or before end_date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_datetime, end_datetime = _date_range(start_date, end_date)
        bucket_days = 1 if (end_date - start_date).days + 1 < 31 else 7
        added_events = Package.objects.filter(
            added_at__gte=start_datetime,
            added_at__lt=end_datetime,
        ).values_list("added_at", flat=True)
        assigned_events = Package.objects.filter(
            assigned_at__gte=start_datetime,
            assigned_at__lt=end_datetime,
        ).values_list("assigned_at", flat=True)
        completed_events = Package.objects.filter(
            delivered_at__gte=start_datetime,
            delivered_at__lt=end_datetime,
        ).values_list("delivered_at", flat=True)
        cancelled_events = PackageStatus.objects.filter(
            status="Cancelled",
            updated_at__gte=start_datetime,
            updated_at__lt=end_datetime,
        ).values_list("updated_at", "package_id")

        metrics = {
            "delivery_orders_added": _metric_series(
                added_events, start_date, end_date, bucket_days
            ),
            "delivery_orders_assigned": _metric_series(
                assigned_events, start_date, end_date, bucket_days
            ),
            "delivery_orders_completed": _metric_series(
                completed_events, start_date, end_date, bucket_days
            ),
            "delivery_orders_cancelled": _metric_series(
                cancelled_events, start_date, end_date, bucket_days, unique_key_index=1
            ),
        }

        return Response(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "interval": "daily" if bucket_days == 1 else "weekly",
                **metrics,
            },
            status=status.HTTP_200_OK,
        )

    def delivery_order_list(self, request):
        try:
            start_date = _parse_metrics_date(
                request.query_params.get("start_date"), "start_date"
            ) if request.query_params.get("start_date") else None
            end_date = _parse_metrics_date(
                request.query_params.get("end_date"), "end_date"
            ) if request.query_params.get("end_date") else None
        except ValueError as error:
            return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        if start_date and end_date and start_date > end_date:
            return Response(
                {"error": "start_date must be on or before end_date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        latest_status = (
            PackageStatus.objects.filter(package=OuterRef("pk"))
            .order_by("-updated_at", "-pk")
            .values("status")[:1]
        )

        packages = Package.objects.select_related(
            "pickup_area", "dropoff_area", "biker__user"
        ).annotate(
            current_status=Subquery(latest_status),
            pending_fast_order=Case(
                When(current_status="Pending", is_fast_delivery=True, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )

        if start_date:
            start_datetime, _ = _date_range(start_date, start_date)
            packages = packages.filter(added_at__gte=start_datetime)
        if end_date:
            _, end_datetime = _date_range(end_date, end_date)
            packages = packages.filter(added_at__lt=end_datetime)

        slug = request.query_params.get("slug", "").strip()
        if slug:
            packages = packages.filter(slug__icontains=slug)

        packages = packages.order_by("-added_at", "pending_fast_order", "-pk")
        paginator = self.DeliveryListPagination()
        page = paginator.paginate_queryset(packages, request, view=self)

        response_data = [
            {
                "id": package.id,
                "slug": package.slug,
                "date_created": package.added_at,
                "pickup_area": package.pickup_area.name if package.pickup_area else None,
                "dropoff_area": package.dropoff_area.name if package.dropoff_area else None,
                "package_status": package.current_status or "Pending",
                "is_fast_delivery": package.is_fast_delivery,
                "driver_name": (
                    f"{package.biker.user.first_name} {package.biker.user.last_name}".strip()
                    if package.biker
                    else None
                ),
            }
            for package in page
        ]

        return paginator.get_paginated_response(response_data)

    def today_delivery_metrics(self, request):
        today = timezone.localdate()

        total_deliveries = Package.objects.filter(
            added_at__date=today,
        ).count()

        fast_deliveries = Package.objects.filter(
            added_at__date=today,
            is_fast_delivery=True,
        ).count()

        unassigned_deliveries = Package.objects.filter(
            added_at__date=today,
            biker__isnull=True,
        ).count()

        delivered_deliveries = PackageStatus.objects.filter(
            status="Delivered",
            package__added_at__date=today,
        ).count()

        cancelled_deliveries = PackageStatus.objects.filter(
            status="Cancelled",
            package__added_at__date=today,
        ).count()

        return Response(
            {
                "total_deliveries": total_deliveries,
                "unassigned_deliveries": unassigned_deliveries,
                "delivered_deliveries": delivered_deliveries,
                "cancelled_deliveries": cancelled_deliveries,
                "fast_deliveries": fast_deliveries,
            },
            status=status.HTTP_200_OK,
        )

