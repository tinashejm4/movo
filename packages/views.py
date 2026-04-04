from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from rest_framework.decorators import api_view
from users.models import Contact, Customer, Shop
from bookkeeping.models import Sale

class Package(APIView):

    def response(self, package):
        response = {
            name = f"{origin_id}{destination_id}-{package.id}"
            sender = sender
            receiver = receiver
            from_shop = origin
            to_shop = destination
            size = size
            price = price
            logged_by = logged_by
        }

    def create_new_customer(self, name, phone_number):
        name_l = name.strip().split(" ")
        first_name = name_l[0]
        last_name = sender_name_l[1]
        new_user = User.objects.create(first_name = first_name, last_name = last_name)
        new_contact = Contact.objects.create(user = new_user, phone_number = phone_number)
        new_customer = Customer.objects.create(user = new_user)

        return new_user        

    def post(self, request):
        #get or create users using phone numbers 
        sender_name = request.data["sender_name"]
        sender_number = request.data["sender_number"]
        receiver_name = request.data["receiver_name"]
        receiver_number = request.data["receiver_number"]

        sender_contact = Contact.objects.filter(phone_number = sender_number)
        receiver_contact = Contact.objects.filter(phone_number = receiver_number)

        if sender_contact.exists:
            sender = self.create_new_customer(sender_name, sender_number)
        if receiver_contact.exists:
            receiver = self.create_new_customer(receiver_name, receiver_number)
        
        # Origin and destinations
        origin_id = request.data["origin_id"]
        destination_id = request.data["destination_id"]

        origin = get_object_or_404(Shop, id = origin_id)
        destination = get_object_or_404(Shop, id = destination_id)

        size = get_object_or_404(Size, id = origin_id)
        price = get_object_or_404(Price, package_size = size)

        #logged by
        logged_by = User.objects.get(id = 1)

        # create package
        package = Package(
        name = f"{origin_id}{destination_id}-{package.id}",
        sender = sender,
        receiver = receiver,
        from_shop = origin,
        to_shop = destination,
        size = size,
        price = price,
        logged_by = logged_by)

        #log sale
        sale = Sale(amount = Price.price, package = package)

        return Response(self.response(package))

@api_view(['GET'])
def check_username(request):
    username = request.GET.get("username", "")
    exists = User.objects.filter(username=username).exists()
    return Response({"available": not exists})

class LoginView(APIView):

    def post(self, request):
        emailOrUsername = request.data.get("emailOrUsername")
        password = request.data.get("password")

        user = authenticate(username=emailOrUsername, password=password)
        if not user:
            user = authenticate(email=emailOrUsername, password=password)

        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "error": ""
            })
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)


