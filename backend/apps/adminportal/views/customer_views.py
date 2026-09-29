from apps.bookkeeping.models import Account
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from apps.users.permissions import IsStaff
from apps.users.models import Biker, Customer
from apps.intracity.models import Package, PackageStatus
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework.pagination import PageNumberPagination



class CustomersMetricsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request, *args, **kwargs):
        total_customers = Customer.objects.filter(user__is_active=True).count()
        deactivated_customers = Customer.objects.filter(user__is_active=False).count()
        new_signups_today = Customer.objects.filter(user__is_active=True, user__date_joined__date=timezone.now().date()).count()
        new_signups_this_month = Customer.objects.filter(user__is_active=True, user__date_joined__date__month=timezone.now().date().month).count()
        #active clients are clients that have made an order in the last 30 days
        active_customers = Package.objects.filter(added_at__gte=timezone.now() - timezone.timedelta(days=30)).values('sender','receiver').distinct().count()

        return Response(
            {
                "total_customers": total_customers,
                "new_signups_today": new_signups_today,
                "new_signups_this_month": new_signups_this_month,
                "active_customers": active_customers,
                "deactivated_customers": deactivated_customers,
            },
            status=status.HTTP_200_OK,
        )


class CustomersListView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]
    
    def get(self, request, *args, **kwargs):
        customers = Customer.objects.filter(user__is_active=True)
        paginator = PageNumberPagination()
        paginator.page_size = 20
        paginated_customers = paginator.paginate_queryset(customers, request, view=self)
        paginated_customers = sorted(paginated_customers, key=lambda c: (Package.objects.filter(sender=c) | Package.objects.filter(receiver=c)).count(), reverse=True)
        customer_data = [
            {
                "id": customer.id,
                "username": customer.user.username,
                "name": f"{customer.user.first_name} {customer.user.last_name}",
                "date_joined": customer.user.date_joined,
                "number_of_orders": (Package.objects.filter(sender=customer) | Package.objects.filter(receiver=customer)).count()
            }
            for customer in paginated_customers
        ]
        return paginator.get_paginated_response(customer_data)

class CustomersDetailView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request, pk, *args, **kwargs):
        customer = get_object_or_404(Customer, pk=pk, user__is_active=True)
        packages = (Package.objects.filter(sender=customer) | Package.objects.filter(receiver=customer)).order_by('-added_at')
        customer_data = {
            "id": customer.id,
            "orders":  [
                {
                    "id": package.id,
                    "tracking_number": package.slug,
                    "sender": package.sender.user.username,
                    "receiver": package.receiver.user.username,
                    "from_suburb": package.pickup_area.name if package.pickup_area else None,
                    "to_suburb": package.dropoff_area.name if package.dropoff_area else None,
                    "status": PackageStatus.objects.filter(package=package).last().status,
                    "created_at": package.added_at,
                } for package in packages[:10]
            ] 
        }
        return Response(customer_data, status=status.HTTP_200_OK)