from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.users.permissions import IsStaff
from apps.transporters.models import BikerDailySession
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.db.models import OuterRef, Subquery
from apps.intracity.models import PackageStatus,Invoice, Package
from apps.users.models import Biker, Branch, Customer, Suburb
import django.utils.timezone as timezone
from logging import getLogger

class MainMetricsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]


    def get(self, request):
        package_statuses = PackageStatus.objects.filter(package=OuterRef("pk"))
        latest_status = package_statuses.order_by("-updated_at", "-pk").values(
            "status"
        )[:1]
        new_customers = Customer.objects.filter(date_joined=timezone.localdate()).count()
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
            "total_new_orders": total_new_orders.count(),
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
                    "biker__user",
                    "sender__user",
                    "receiver__user",
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
            biker_details.append({
                "biker_id": biker.id,
                "biker_name": biker.user.first_name + " " + biker.user.last_name,
                "is_active": True if session else False,
                "is_busy": True if current_package else False,
                "started_at": session.start_time if session else None,
                "num_packages_assigned": packages_assigned_today,
                "num_packages_delivered": packages_delivered_today,
            })
        return JsonResponse(biker_details, safe=False)

class PackageListView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        packages = Package.objects.filter(added_at__date=timezone.localdate())

        package_list = []
        for package in packages:
            package_statuses = PackageStatus.objects.filter(package=package).order_by("-updated_at", "-pk")
            status_history = list(package_statuses.values("status", "updated_at"))
            invoice = Invoice.objects.filter(package=package).first()
            package_list.append({
                "package_id": package.id,
                "slug": package.slug,
                "pickup_area": Suburb.objects.get(id = package.pickup_area.id).name,
                "dropoff_area": Suburb.objects.get(id = package.dropoff_area.id).name,
                "current_status": status_history[0]["status"] if status_history else None,
                "is_fast_delivery": package.is_fast_delivery,
                "invoice_amount": invoice.amount if invoice else None,
            })
        return JsonResponse({
            "packages": package_list
        })

class PackageDetailsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        package_id = request.GET.get("package_id")
        package = Package.objects.filter(id=package_id).first()
        if not package:
            return JsonResponse({"error": "Package not found"}, status=404)

        package_statuses = PackageStatus.objects.filter(package=package).order_by("-updated_at", "-pk")
        status_history = list(package_statuses.values("status", "updated_at"))
        invoice = Invoice.objects.filter(package=package).first()

        logger = getLogger(__name__)
        logger.warning(f"Fetching details for package ID: {status_history}")

        package_details = {
            "package_id": package.id,
            "slug": package.slug,
            "sender": package.sender.user.get_full_name(),
            "sender_phone": f"0{package.sender.user.username}",
            "receiver": package.receiver.user.get_full_name(),
            "receiver_phone": f"0{package.receiver.user.username}",
            "pickup_area": Suburb.objects.get(id = package.pickup_area.id).name,
            "pickup_address": package.pickup_address,
            "dropoff_area": Suburb.objects.get(id = package.dropoff_area.id).name,
            "dropoff_address": package.dropoff_address,
            "comments": package.comments,
            "status_history": status_history,
            "current_status": status_history[0]["status"] if status_history else None,
            "invoice_id": invoice.id if invoice else None,
            "payment_method": invoice.payment_method if invoice else None,
            "is_paid": invoice.is_paid if invoice else None,
            "paid_at": invoice.paid_at if invoice else None,
        }
        return JsonResponse({"package": package_details})