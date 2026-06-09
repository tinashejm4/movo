import random
import string

from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from rest_framework.decorators import api_view
from users.models import Contact, Customer, Branch, Staff
from .models import Package, Batch,PrePackage, Price, PackageDimension
# from bookkeeping.models import Sale, TransportPayment, DropOffPayment,PickUpPayment,ReceipientCode
import datetime

class CreatePrePackage(APIView):
    permission_classes = [IsAuthenticated]

    def generate_code(self):
        letters = ''.join(random.choices(string.ascii_uppercase, k=3))
        numbers = ''.join(random.choices(string.digits, k=3))
        return f"{letters}{numbers}"

    def post(self, request):
        data = request.data

        sender_number = data.get("sender_number")
        receiver_name = data.get("receiver_name")
        receiver_number = data.get("receiver_number")
        receiving_shop_id = data.get("receiving_shop_id")
        description = data.get("description")
        self_created = data.get("self_created")

        code = self.generate_code()
        while PrePackage.objects.filter(creation_code = code).exists():
            code = self.generate_code()

        if not Contact.objects.filter(phone_number = sender_number).exists():
            sender, sender_contact = self.create_new_customer(sender_number)  
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
            description = description
        )
        response = {
            "message": "Pre-package created successfully",
            "code": code
        }
        return Response(response, status = status.HTTP_201_CREATED)

    def create_new_customer(self, phone_number, name = None):
        if not name:
            name = "Unknown"
        first_name = name.strip().split(" ")[0]
        last_name = name.strip().split(" ")[1] if len(name.strip().split(" ")) > 1 else ""
        user = User.objects.create(first_name = first_name, last_name = last_name)
        contact = Contact.objects.create(user = user, phone_number = phone_number)
        customer = Customer.objects.create(user = user)
        return customer, contact

# class Package(APIView):

#     permission_classes = [IsAuthenticated]

#     def response(self, package):
#         response = {
#             "name": f"{package.batch.id:04}-{package.id:04}",
#             "sender": sender,
#             "receiver": receiver,
#             "from_shop": origin,
#             "to_shop": destination,
#             "size": size,
#             "price": price,
#             "logged_by": logged_by
#         }
#         return response

#     def create_new_customer(self, name, phone_number):
#         name_l = name.strip().split(" ")
#         first_name = name_l[0]
#         last_name = sender_name_l[1]
#         new_user = User.objects.create(first_name = first_name, last_name = last_name)
#         new_contact = Contact.objects.create(user = new_user, phone_number = phone_number)
#         new_customer = Customer.objects.create(user = new_user)

#         return new_user        

#     def is_batch_full(self, batch):
#         #logic to check the volume of packages depending on the 
#         return False

#     def post(self, request):
#         #get or create users using phone numbers 
#         sender_name = request.data["sender_name"]
#         sender_number = request.data["sender_number"]
#         receiver_name = request.data["receiver_name"]
#         receiver_number = request.data["receiver_number"]

#         sender_contact = Contact.objects.filter(phone_number = sender_number)
#         receiver_contact = Contact.objects.filter(phone_number = receiver_number)

#         if sender_contact.exists:
#             sender = self.create_new_customer(sender_name, sender_number)
#         if receiver_contact.exists:
#             receiver = self.create_new_customer(receiver_name, receiver_number)
        
#         # Origin and destinations
#         origin_id = request.data["origin_id"]
#         destination_id = request.data["destination_id"]

#         origin = get_object_or_404(Shop, id = origin_id)
#         destination = get_object_or_404(Shop, id = destination_id)

#         size = get_object_or_404(Size, id = origin_id)
#         price = get_object_or_404(Price, package_size = size)

#         #logged by
#         logged_by = User.objects.get(id = 1)

#         #Batch Creation
#         batch = Batch.objects.filter(origin_location = origin, destination_location = destination, is_available = True)
#         if not batch.exists:
#             batch = Batch.objects.create(origin_location = origin, destination_location = destination)

#         # create package
#         package = Package(
#             name = f"{origin_id}{destination_id}-{package.id}",
#             sender = sender,
#             receiver = receiver,
#             size = size,
#             price = price,
#             logged_by = logged_by
#         )

#         #Close batch if full
#         if self.is_batch_full(batch):
#             batch.is_available = False
#             batch.save()

#         # Create receipient otp code and send on whatsapp
#         receipient_otp_code = ReceipientCode.objects.create(package = package)


#         #log sale
#         sale = Sale.objects.create(amount = Price.price, package = package)

#         return Response(self.response(package))

#     def get(self, request):
#         package_id = request.data.get["id"]
#         package = Package.objects.get(id = package_id)
#         return Response(self.response(package))

# class Batch(APIView):

#     def get(self, request):
#         batch_id = request.data.get["id"]
#         batch = Batch.objects.get(id = batch_id)
        
#         packages = Package.objects.filter(batch = batch)
#         package_results = []
#         for package in packages:
#             package_results.append(
#                 {   
#                     package_id: package.id,
#                     package_name: package.name,
#                     size: package.size,
#                     logged_by: package.logged_by,
#                     date_added: package.date_added
#                 }
#             ) 

#         response = {
#             "batch_id", f"{batch.id:04}",
#             "from_shop": origin_location.name,
#             "to_shop": destination_location.name,
#             "date_added": batch.date_added, 
#             "status": batch.is_available,
#             "packages": package_results
#         }
        
#         return Response(response)

# class Trip(APIView):

#     def round_to_half(self,x):
#         return round(x * 2) / 2

#     def post(self, request):
#         batch_id = request.data.get["id"]
#         batch = Batch.objects.get(id = batch_id)
#         distance_from_cbd = destination_location.distance_from_cbd
#         rate = Rate.objects.all().last
#         cost = round_to_half(distance_from_cbd * rate.rate)
#         trip = Trip.objects.create(batch = batch, cost = cost, rate = rate)
        
#         # TO DO for driver you will need to send messages to a new driver every 2 minutes so they accept 
#         #notify clients package has been picked up
#         # create payment to driver
#         payment = TransportPayment.objects.create(amount = cost, batch = batch)

#         # create code for driver and send
#         code = DriverCode.objects.create(batch= batch)
#         return ({"cost": cost})

#     def get(self, request):
#         batch_id = request.data.get["id"]
#         batch = Batch.objects.get(id = batch_id)

#         trip = Trip.objects.get(batch = batch)
#         return ({"cost": trip.cost})

# class EndTrip(APIView):

#     def post(self, request):
#         batch_id = request.data.get["batch_id"]
#         trip_id = request.data.get["trip_id"]
#         trip = Trip.objects.get(id = trip_id)
#         trip.ended = True
#         trip.ended_at = datetime.datetime.now()
        
#         batch = Batch,objects.get(id = batch_id)
#         #get bath details
#         num_packages = Package.objects.filter(batch = batch)
#         dropoff_amount = Rate.objects.all().last.dropoff_amount * num_packages

#         #credit amount to collection point
#         dropoff_payment = DropOffPayment.objects.create(amount = dropoff_amount, batch = batch)

#         # send whatsapp message to the collectin point

#         return Response({})

# class PackagePickup(APIView):

#     def post(self, request):
#         package_id = request.data.get["package_id"]
        
#         package = Package.objects.get(id = package_id)

#         #edit package details
#         package.collected = True
#         package.collected_at = datetime.datetime.now()
#         package.save()


#         #credit amount to collection point
#         pickup_payment = PickUpPayment.objects.create(amount = dropoff_amount, package = package)

#         # send whatsapp message to the collectin point with
#         # send message to ustomer notifying of their collection

#         return Response({})