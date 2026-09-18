from apps.bookkeeping.models import Account
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.users.permissions import IsStaff
from apps.users.models import Biker, Contact, NextOfKin, ProfileImage, Identification, Licence, Branch
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404

class BikersListView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        bikers = Biker.objects.all()
        data = [
            {
                "biker_user_id": biker.user.id,
                "id": biker.id,
                "username": biker.user.username,
                "name": biker.user.first_name + " " + biker.user.last_name,
                "profile_picture": ProfileImage.objects.filter(user=biker.user).first().profile_image.url if ProfileImage.objects.filter(user=biker.user).exists() else None,
            }
            for biker in bikers
        ]
        return Response(data, status=status.HTTP_200_OK)

class BikerDetailView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request, biker_user_id):
        biker_user = get_object_or_404(User, id=biker_user_id)
        biker = get_object_or_404(Biker, user = biker_user)
        contact = get_object_or_404(Contact, user=biker_user)
        next_of_kin = get_object_or_404(NextOfKin, user=biker_user)
        profile_image = get_object_or_404(ProfileImage, user=biker_user)
        identification = get_object_or_404(Identification, user=biker_user)
        licence = get_object_or_404(Licence, user=biker_user)
        data = {
            "id": biker.id,
            "name": biker_user.first_name + " " + biker_user.last_name,
            "username": biker_user.username,
            "phone_number1": contact.phone_number,
            "phone_number2": contact.phone_number2,
            "address": contact.address,
            "started_on": biker_user.date_joined,
            "next_of_kin": {
                "name": next_of_kin.name,
                "phone_number": next_of_kin.phone_number,
                "relationship": next_of_kin.relationship,
            },
            "profile_picture": profile_image.profile_image.url if profile_image else None,
            "id_picture": identification.id_image.url if identification else None,
            "id_number": identification.id_number if identification else None,
            "licence_picture": licence.licence_image.url if licence else None,
            "licence_number": licence.licence_number if licence else None,
        }
        return Response(data, status=status.HTTP_200_OK)

class BikerCreateView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

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
            phone_number=phone_number1,
            phone_number2=phone_number2,
            address=address,
        )

        NextOfKin.objects.create(
            user=biker_user,
            name=next_of_kin_name,
            phone_number=next_of_kin_phone_number,
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
            currency = "USD",
        )

        Account.objects.create(
            name=f"{first_name} {last_name}'s Cash Account",
            branch=branch,
            owner=biker_user,
            description = f"Daily Cash Account for {first_name} {last_name}"
        )


        return Response({"detail": "Biker created successfully"}, status=status.HTTP_201_CREATED)


class BikerStatisticsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        total_bikers = Biker.objects.count()
        active_bikers = Biker.objects.filter(is_active=True).count()
        inactive_bikers = Biker.objects.filter(is_active=False).count()

        data = {
            "total_bikers": total_bikers,
            "active_bikers": active_bikers,
            "inactive_bikers": inactive_bikers,
        }
        return Response(data, status=status.HTTP_200_OK)

