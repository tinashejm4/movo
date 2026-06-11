import random
import string
import math
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from rest_framework.decorators import api_view
from users.models import Contact, Customer, Branch, Staff
from .models import Package, Batch, Payment,PrePackage, Price, PackageDimension
from users.permissions import IsStaff
# from bookkeeping.models import Sale, TransportPayment, DropOffPayment,PickUpPayment,ReceipientCode
import datetime

class PrePackageView(APIView):
    # permission_classes = [IsAuthenticated]

    def generate_code(self):
        letters = ''.join(random.choices(string.ascii_uppercase, k=2))
        numbers = ''.join(random.choices(string.digits, k=3))
        return f"{letters}{numbers}"

    def post(self, request):
        data = request.data

        sender_number = data.get("sender_number")
        receiver_name = data.get("receiver_name")
        receiver_number = data.get("receiver_number")
        receiving_shop_id = data.get("receiving_shop_id")
        self_created = data.get("self_created")

        code = self.generate_code()
        while PrePackage.objects.filter(creation_code = code).exists():
            code = self.generate_code()

        if not Contact.objects.filter(phone_number = sender_number).exists():
            sender, sender_contact = self.create_new_customer(sender_number, sender_number)  
        else:
            sender_user = Contact.objects.get(phone_number = sender_number).user 
            sender = Customer.objects.get(user = sender_user)

        if not Contact.objects.filter(phone_number = receiver_number).exists():
            receiver, receiver_contact = self.create_new_customer(receiver_number, receiver_name)  
        else:
            receiver_user = Contact.objects.get(phone_number = receiver_number).user
            receiver = Customer.objects.get(user = receiver_user)

        PrePackage.objects.create(
            creation_code = code,
            sender = sender,
            receiver = receiver,
            to_shop = get_object_or_404(Branch, id = receiving_shop_id),
            self_created = self_created,
        )
        response = {
            "message": "Pre-package created successfully",
            "code": code
        }
        return Response(response, status = status.HTTP_201_CREATED)

    def create_new_customer(self, phone_number, name = None):
        if not name:
            name = "Unknown"
            first_name = name
            last_name = ""
        else:
            first_name = name.strip().split(" ")[0]
            last_name = name.strip().split(" ")[1] if len(name.strip().split(" ")) > 1 else ""
        
        user = User.objects.create(username = phone_number, first_name = first_name, last_name = last_name)
        contact = Contact.objects.create(user = user, phone_number = phone_number)
        customer = Customer.objects.create(user = user)
        return customer, contact


class PackageView(APIView):

    permission_classes = [IsAuthenticated, IsStaff]
    dimensional_factor = 5000

    def get(self, request):
        package_id = request.data.get("id")
        package = get_object_or_404(Package, id = package_id)
        response = {
            "name": f"{package.batch.id:04}-{package.id:04}",
            "sender": package.sender,
            "receiver": package.receiver,
            "from_shop": package.batch.sent_from_shop,
            "to_shop": package.batch.sent_to_shop,
            "size": package.dimensions.get_size(),
            "price": package.price,
            "logged_by": package.logged_by
        }
        return Response(response)
    
    def generate_code(self):
        letters = ''.join(random.choices(string.ascii_uppercase, k=1))
        numbers = ''.join(random.choices(string.digits, k=5))
        return f"{letters}{numbers}"
    
    def post(self, request):
        data = request.data
        print(data)

        pre_package_code = data.get("pre_package_code")
        dimensions_length = data.get("length")
        dimensions_width = data.get("width")
        dimensions_height = data.get("height")
        dimensions_weight = data.get("weight")
        description = data.get("description"),
        is_pay_forward = data.get("is_pay_forward")

        pre_package = get_object_or_404(PrePackage, creation_code = pre_package_code)

        dimensions = PackageDimension.objects.create(
            length = dimensions_length, 
            width = dimensions_width, 
            height = dimensions_height, 
            weight = dimensions_weight,
            dimensional_factor = self.dimensional_factor
            )
        price = Price.objects.all().last()

        batch = Batch.objects.filter(sent_from_shop = pre_package.to_shop, sent_to_shop = pre_package.to_shop, is_available = True).first()
        if not batch:
            batch = Batch.objects.create(sent_from_shop = pre_package.to_shop, sent_to_shop = pre_package.to_shop)

        payment = Payment.objects.create(
            price = price, 
            amount = math.ceil(price.base_fee + price.insurance_fee + (price.rate_per_kg * dimensions.get_charged_weight())), 
            is_pay_forward = is_pay_forward)
        
        receiver_code = self.generate_code()

        package = Package.objects.create(
            pre_package = pre_package,
            batch = batch,
            dimensions = dimensions,
            payment = payment,
            receiver_code = receiver_code,
            description = description,
            logged_by = request.user
        )

        response = {
            "message": "Package created successfully",
            "package_name": f"{package.batch.id:04}-{package.id:04}"
        }
        return Response(response, status=status.HTTP_201_CREATED)
