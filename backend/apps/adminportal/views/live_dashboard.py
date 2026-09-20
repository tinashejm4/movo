from apps.bookkeeping.models import Account
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.users.permissions import IsStaff
from apps.users.models import Biker, Branch, Customer
from apps.intracity.models import Package
from apps.transporters.models import BikerDailySession
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.http import JsonResponse
from django.db.models import OuterRef, Subquery
from apps.intracity.models import PackageStatus
import django.utils.timezone as timezone

class MainMetricsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]


    def get(self, request):
        package_statuses = PackageStatus.objects.filter(package=OuterRef("pk"))
        latest_status = package_statuses.order_by("-updated_at", "-pk").values(
            "status"
        )[:1]
        new_customers = Customer.objects.filter(date_joined__date=timezone.localdate()).count()
        total_new_orders = Package.objects.filter(added_at__date=timezone.localdate()).annotate(
            latest_status=Subquery(latest_status),
        )

        delivered_orders = 0
        canceled_orders = 0
        in_transit_orders = 0
        assigned_orders = 0

        for package in total_new_orders:
            if package.latest_status == "Delivered":
                delivered_orders += 1
            elif package.latest_status == "Canceled":
                canceled_orders += 1
            elif package.latest_status == "In Transit":
                in_transit_orders += 1
            elif package.latest_status == "Assigned":
                assigned_orders += 1

        # return new customers, oders placed

        return JsonResponse({
            "new_customers": new_customers,
            "total_new_orders": total_new_orders.count,
            "delivered_orders": delivered_orders,
            "canceled_orders": canceled_orders,
            "in_transit_orders": in_transit_orders,
            "assigned_orders": assigned_orders,
        })

class BikerMetricsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        package_statuses = PackageStatus.objects.filter(package=OuterRef("pk"))
        latest_status = package_statuses.order_by("-updated_at", "-pk").values(
            "status"
        )[:1]

        bikers = Biker.objects.all()
        biker_details = []

        for biker in bikers:
            current_package = (
                Package.objects.filter(biker__user=biker.user)
                .select_related(
                    "slug"
                    "biker__user",
                    "sender__user",
                    "receiver__user",
                    "delivered_at",
                    "pickup_area",
                    "dropoff_area",
                )
                .annotate(current_status=Subquery(latest_status))
                .filter(current_status__in=["Pending", "Assigned", "In Transit"])
                .filter(assigned_at__date=timezone.localdate())
                .order_by("-assigned_at", "-added_at")
                .first()
            )

            # packages assigned to the biker today
            packages_assigned_today = Package.objects.filter(
                biker__user=biker.user,
                assigned_at__date=timezone.localdate()
            ).count()

            packages_delivered_today = Package.objects.filter(
                biker__user=biker.user,
                delivered_at__isnull=False,
                assigned_at__date=timezone.localdate()
            ).count()

            session = BikerDailySession.objects.filter(biker=biker, is_active=True).first()
            active_status = True if session else False
            biker_details.append({
                "biker_id": biker.id,
                "biker_name": biker.user.first_name + " " + biker.user.last_name,
                "active_status": active_status,
                "is_busy": True if current_package else False,
                "started_at": session.start_time if session else None,
                "num_packages_assigned": packages_assigned_today,
                "num_packages_delivered": packages_delivered_today,
            })
        return JsonResponse({
            "details": biker_details,
        })