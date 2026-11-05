from apps.bookkeeping.models import Account
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.users.permissions import IsStaff
from apps.users.models import Biker, Contact, NextOfKin, ProfileImage, Identification, Licence, Branch
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from apps.transporters.models import BikerDailySession
from apps.transporters.shift_service import effective_shift, shift_allows_work
from apps.users.utils import is_valid_zimbabwean_number,normalize_zimbabwean_number


class BikerListItemSerializer(serializers.Serializer):
    biker_user_id = serializers.IntegerField()
    id = serializers.IntegerField()
    username = serializers.CharField()
    name = serializers.CharField()
    profile_picture = serializers.CharField(allow_null=True)


class EffectiveShiftSerializer(serializers.Serializer):
    date = serializers.DateField()
    is_open = serializers.BooleanField()
    start_time = serializers.TimeField(allow_null=True)
    end_time = serializers.TimeField(allow_null=True)
    source = serializers.ChoiceField(choices=("exception", "weekly"))


class NextOfKinSerializer(serializers.Serializer):
    name = serializers.CharField(allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(allow_null=True, allow_blank=True)
    relationship = serializers.CharField(allow_null=True, allow_blank=True)


class BikerDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    username = serializers.CharField()
    phone_number1 = serializers.CharField(allow_null=True, allow_blank=True)
    phone_number2 = serializers.CharField(allow_null=True, allow_blank=True)
    address = serializers.CharField(allow_null=True, allow_blank=True)
    started_on = serializers.DateTimeField()
    next_of_kin = NextOfKinSerializer(allow_null=True)
    profile_picture = serializers.CharField(allow_null=True)
    id_picture = serializers.CharField(allow_null=True)
    id_number = serializers.CharField(allow_null=True)
    licence_picture = serializers.CharField(allow_null=True)
    licence_number = serializers.CharField(allow_null=True)
    effective_shift = EffectiveShiftSerializer()


class BikerCreateRequestSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    username = serializers.CharField()
    branch = serializers.IntegerField(help_text="ID of the biker's branch.")
    profile_picture = serializers.ImageField()
    phone_number1 = serializers.CharField()
    phone_number2 = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    address = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    next_of_kin_name = serializers.CharField()
    next_of_kin_phone_number = serializers.CharField()
    next_of_kin_relationship = serializers.CharField()
    id_picture = serializers.ImageField()
    id_number = serializers.CharField()
    licence_picture = serializers.ImageField()
    licence_number = serializers.CharField()


class BikerStatisticsSerializer(serializers.Serializer):
    total_bikers = serializers.IntegerField()
    active_bikers = serializers.IntegerField()
    inactive_bikers = serializers.IntegerField()


class BikerCreateResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()



class BikersListView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @extend_schema(tags=["Admin/Bikers"], operation_id="admin_bikers_list", responses={200: BikerListItemSerializer(many=True)})
    def get(self, request):
        bikers = Biker.objects.all()
        data = []
        for biker in bikers:
            profile_image = ProfileImage.objects.filter(user=biker.user).first()
            image_url = profile_image.profile_image.url if profile_image and profile_image.profile_image else None
            data.append({
                "biker_user_id": biker.user.id,
                "id": biker.id,
                "username": biker.user.username,
                "name": biker.user.first_name + " " + biker.user.last_name,
                "profile_picture": request.build_absolute_uri(image_url) if image_url else None,
            })
        return Response(data, status=status.HTTP_200_OK)

class BikerDetailView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @extend_schema(
        tags=["Admin/Bikers"], operation_id="admin_biker_detail",
        parameters=[OpenApiParameter("biker_user_id", int, OpenApiParameter.PATH, description="User ID of the biker.")],
        responses={200: BikerDetailSerializer},
    )
    def get(self, request, biker_user_id):
        biker_user = get_object_or_404(User, id=biker_user_id)
        biker = get_object_or_404(Biker, user = biker_user)
        contact = Contact.objects.filter(user=biker_user).first()
        next_of_kin = NextOfKin.objects.filter(user=biker_user).first()
        profile_image = ProfileImage.objects.filter(user=biker_user).first()
        identification = Identification.objects.filter(user=biker_user).first()
        licence = Licence.objects.filter(user=biker_user).first()
        profile_url = profile_image.profile_image.url if profile_image and profile_image.profile_image else None
        id_url = identification.id_image.url if identification and identification.id_image else None
        licence_url = licence.licence_image.url if licence and licence.licence_image else None
        data = {
            "id": biker.id,
            "name": biker_user.first_name + " " + biker_user.last_name,
            "username": biker_user.username,
            "phone_number1": contact.phone_number if contact else None,
            "phone_number2": contact.phone_number2 if contact else None,
            "address": contact.address if contact else None,
            "started_on": biker_user.date_joined,
            "next_of_kin": {
                "name": next_of_kin.name,
                "phone_number": next_of_kin.phone_number,
                "relationship": next_of_kin.relationship,
            } if next_of_kin else None,
            "profile_picture": request.build_absolute_uri(profile_url) if profile_url else None,
            "id_picture": request.build_absolute_uri(id_url) if id_url else None,
            "id_number": identification.id_number if identification else None,
            "licence_picture": request.build_absolute_uri(licence_url) if licence_url else None,
            "licence_number": licence.licence_number if licence else None,
            "effective_shift": effective_shift(biker, timezone.localdate()),
        }
        return Response(data, status=status.HTTP_200_OK)


class BikerCreateView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @transaction.atomic
    @extend_schema(
        tags=["Admin/Bikers"], operation_id="admin_biker_create",
        request={"multipart/form-data": BikerCreateRequestSerializer},
        responses={201: BikerCreateResponseSerializer},
    )
    def post(self, request):
        first_name = request.data.get("first_name")
        last_name = request.data.get("last_name")
        username = request.data.get("username")
        branch_id = request.data.get("branch")
        profile_picture = request.data.get("profile_picture")

        phone_number1 = request.data.get("phone_number1")
        phone_number2 = request.data.get("phone_number2")
        address = request.data.get("address")

        next_of_kin_name = request.data.get("next_of_kin_name")
        next_of_kin_phone_number = request.data.get("next_of_kin_phone_number")
        next_of_kin_relationship = request.data.get("next_of_kin_relationship")

        id_picture = request.data.get("id_picture")
        id_number = request.data.get("id_number")
        licence_picture = request.data.get("licence_picture")
        licence_number = request.data.get("licence_number")

        biker_user = User.objects.create(
            first_name=first_name,
            last_name=last_name,
            username=username,
        )

        Contact.objects.create(
            user=biker_user,
            phone_number=normalize_zimbabwean_number(phone_number1),
            phone_number2=normalize_zimbabwean_number(phone_number2) if phone_number2 else None,
            address=address,
        )

        NextOfKin.objects.create(
            user=biker_user,
            name=next_of_kin_name,
            phone_number=normalize_zimbabwean_number(next_of_kin_phone_number),
            relationship=next_of_kin_relationship,
        )

        ProfileImage.objects.create(
            user=biker_user,
            profile_image=profile_picture,
        )

        Identification.objects.create(
            user=biker_user,
            id_image=id_picture,
            id_number=id_number,
        )

        Licence.objects.create(
            user=biker_user,
            licence_image=licence_picture,
            licence_number=licence_number,
        )

        branch = get_object_or_404(Branch, id=branch_id)
        Biker.objects.create(
            user=biker_user,
            branch=branch,
        )

        Account.objects.create(
            name=f"{first_name} {last_name}'s Cash Account",
            branch=branch,
            owner=biker_user,
            currency = "USD",
            description = f"Daily Cash Account for {first_name} {last_name}"
        )


        return Response({"detail": "Biker created successfully"}, status=status.HTTP_201_CREATED)


class BikerStatisticsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @extend_schema(tags=["Admin/Bikers"], operation_id="admin_biker_statistics", responses={200: BikerStatisticsSerializer})
    def get(self, request):
        total_bikers = Biker.objects.count()
        today = timezone.localdate()
        now = timezone.now()
        active_sessions = BikerDailySession.objects.filter(
            date=today,
            is_active=True,
        ).select_related("biker")
        active_bikers = sum(
            1
            for session in active_sessions
            if shift_allows_work(effective_shift(session.biker, today), now)
        )
        inactive_bikers = total_bikers - active_bikers

        data = {
            "total_bikers": total_bikers,
            "active_bikers": active_bikers,
            "inactive_bikers": inactive_bikers,
        }
        return Response(data, status=status.HTTP_200_OK)

