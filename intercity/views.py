import base64
import os
import json
import random
import string
import math
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from rest_framework.decorators import api_view
from users.models import Contact, Customer, Branch, Staff
from .models import Package, Batch, Payment,PrePackage, Price, PackageDimension, PaymentRequest, ExchangeRate
from users.permissions import IsStaff
from bookkeeping.models import Account, Expense, TransportExpense, ExpenseType
import datetime


def normalize_ecocash_phone(phone: str) -> str:
    if not phone:
        return phone
    phone = str(phone).strip()
    if phone.startswith('+'):
        phone = phone[1:]
    if phone.startswith('0'):
        return '263' + phone[1:]
    return phone


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

class ReceivePackageView(APIView):
    """
    Multi-step package receiving workflow
    
    Step 1: GET - Search package by code to get sender/receiver details
    Step 2: POST - Add package dimensions and description
    Step 3: POST - Finalize with payment information
    """
    
    permission_classes = [IsAuthenticated, IsStaff]
    dimensional_factor = 5000

    def get(self, request):
        """
        Step 1: Search for package by code and retrieve details
        
        Query params: package_code
        Returns: sender details, receiver details, collection point, date added
        """
        package_code = request.query_params.get("package_code")
        
        if not package_code:
            return Response(
                {"error": "package_code is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            pre_package = PrePackage.objects.get(creation_code=package_code)
        except PrePackage.DoesNotExist:
            return Response(
                {"error": "Package not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        sender_contact = Contact.objects.get(user=pre_package.sender.user)
        receiver_contact = Contact.objects.get(user=pre_package.receiver.user)
        
        response = {
            "package_code": package_code,
            "sender_name": f"{pre_package.sender.user.first_name} {pre_package.sender.user.last_name}",
            "sender_phone": sender_contact.phone_number,
            "receiver_name": f"{pre_package.receiver.user.first_name} {pre_package.receiver.user.last_name}",
            "receiver_phone": receiver_contact.phone_number,
            "collection_point": pre_package.to_shop.name,
            "collection_point_id": pre_package.to_shop.id,
            "date_added": pre_package.added_at.isoformat(),
        }
        
        return Response(response, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Step 2 & 3: Add dimensions, description, and payment details, then finalize
        
        Required fields:
        - package_code: Pre-package creation code
        - step: "dimensions" for step 2, "payment" for step 3
        
        Step 2 (dimensions):
        - length, width, height, weight
        - description
        
        Step 3 (payment):
        - is_pay_forward: boolean
        - payment_method: "cash" or "ecocash"
        - currency: "usd" or "zwl"
        """
        data = request.data
        package_code = data.get("package_code").strip()
        step = data.get("step", "payment")  # default to payment for backward compatibility
        
        if not package_code:
            return Response(
                {"error": "package_code is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            print("Pre-package found:", package_code)

            pre_package = PrePackage.objects.get(creation_code=package_code)
        except PrePackage.DoesNotExist:
            print("here is the error 404")
            return Response(
                {"error": "Package not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if step == "dimensions":
            # Step 2: Store dimensions and description temporarily
            # In a real app, you might store these in a cache or session
            # For now, we'll validate the data
            length = data.get("length")
            width = data.get("width")
            height = data.get("height")
            weight = data.get("weight")
            description = data.get("description", "")
            
            if not all([length, width, height, weight]):
                return Response(
                    {"error": "length, width, height, and weight are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                length = float(length)
                width = float(width)
                height = float(height)
                weight = float(weight)
            except ValueError:
                return Response(
                    {"error": "Dimensions must be numeric values"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # compute price for these dimensions so frontend can display it
            price = Price.objects.all().last()
            if not price:
                # create a default price configuration to avoid blocking the workflow
                price = Price.objects.create()

            # temporary PackageDimension instance (not saved) to compute charged weight
            charged_weight = max(float(weight), (float(length) * float(width) * float(height)) / self.dimensional_factor)
            amount = math.ceil(price.base_fee + price.insurance_fee + (price.rate_per_kg * charged_weight))

            # compute ZWL equivalent using latest exchange rate
            exchange = ExchangeRate.objects.all().last()
            if exchange:
                amount_zwl = math.ceil(exchange.convert_usd_to_zwl(amount))
            else:
                amount_zwl = None

            return Response({
                "message": "Dimensions validated. Proceed to payment step.",
                "package_code": package_code,
                "dimensions": {
                    "length": length,
                    "width": width,
                    "height": height,
                    "weight": weight,
                    "description": description
                },
                "amount_usd": amount,
                "amount_zwl": amount_zwl,
                "currency": "usd"
            }, status=status.HTTP_200_OK)
        
        elif step == "payment":
            # Step 3: Create the package with all details
            length = data.get("length")
            width = data.get("width")
            height = data.get("height")
            weight = data.get("weight")
            description = data.get("description", "")
            is_pay_forward = data.get("is_pay_forward", False)
            payment_method = data.get("payment_method", "cash")
            currency = data.get("currency", "usd")
            
            # Validate payment fields
            if payment_method not in ["cash", "ecocash"]:
                return Response(
                    {"error": "payment_method must be 'cash' or 'ecocash'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if currency not in ["usd", "zwl"]:
                return Response(
                    {"error": "currency must be 'usd' or 'zwl'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate dimensions
            if not all([length, width, height, weight]):
                return Response(
                    {"error": "length, width, height, and weight are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                length = float(length)
                width = float(width)
                height = float(height)
                weight = float(weight)
            except ValueError:
                return Response(
                    {"error": "Dimensions must be numeric values"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create dimensions
            dimensions = PackageDimension.objects.create(
                length=length,
                width=width,
                height=height,
                weight=weight,
                dimensional_factor=self.dimensional_factor
            )
            
            # Get current price configuration
            price = Price.objects.all().last()
            if not price:
                # create a default price configuration to avoid blocking the workflow
                price = Price.objects.create()
            
            # Calculate amount
            charged_weight = dimensions.get_charged_weight()
            amount = math.ceil(price.base_fee + price.insurance_fee + (price.rate_per_kg * charged_weight))
            
            # Create payment
            payment = Payment.objects.create(
                price=price,
                amount=amount,
                is_pay_forward=is_pay_forward,
                payment_method=payment_method,
                currency=currency
            )

            from_shop = Staff.objects.get(user=request.user).branch
            
            # Get or create batch
            batch = Batch.objects.filter(
                sent_from_shop=from_shop,
                sent_to_shop=pre_package.to_shop,
                is_available=True
            ).first()
            if not batch:
                batch = Batch.objects.create(
                    sent_from_shop=from_shop,
                    sent_to_shop=pre_package.to_shop
                )
            
            # Generate receiver code
            while True:
                receiver_code = self.generate_code()
                if not Package.objects.filter(receiver_code=receiver_code).exists():
                    break

            # Create package
            package = Package.objects.create(
                pre_package=pre_package,
                batch=batch,
                dimensions=dimensions,
                payment=payment,
                receiver_code=receiver_code,
                description=description,
                logged_by=request.user
            )

            if not is_pay_forward:
                # Record sale in bookkeeping
                account_instance = Account.objects.get(branch=from_shop, currency=currency.upper())
                Sale.objects.create(
                    account=account_instance,
                    payment=payment,
                    amount=amount,
                    added_by=request.user
                )
            
            response = {
                "message": "Package received successfully",
                "package_id": package.id,
                "package_name": f"{package.batch.id:04}-{package.id:04}",
                "receiver_code": receiver_code,
                "amount_usd": amount,
                "amount_zwl": (math.ceil(ExchangeRate.objects.all().last().convert_usd_to_zwl(amount)) if ExchangeRate.objects.all().last() else None),
                "currency": currency,
                "payment_method": payment_method,
                "is_pay_forward": is_pay_forward,
            }


            return Response(response, status=status.HTTP_201_CREATED)
        
        else:
            return Response(
                {"error": "Invalid step. Must be 'dimensions' or 'payment'"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def generate_code(self):
        """Generate a unique receiver code"""
        letters = ''.join(random.choices(string.ascii_uppercase, k=1))
        numbers = ''.join(random.choices(string.digits, k=5))
        return f"{letters}{numbers}"

class RequestPaymentView(APIView):
    """Create a PaymentRequest (simulates requesting mobile money payment)"""

    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request):
        data = request.data
        package_code = data.get('package_code')
        amount = data.get('amount')
        method = data.get('method')
        phone = data.get('phone_number')
        currency = data.get('currency', 'usd')

        if not all([package_code, amount, method]):
            return Response({'error': 'package_code, amount and method are required'}, status=status.HTTP_400_BAD_REQUEST)

        if method == 'ecocash' and not phone:
            return Response({'error': 'phone_number is required for EcoCash payments'}, status=status.HTTP_400_BAD_REQUEST)


        try:
            float(amount)
        except (TypeError, ValueError):
            return Response({'error': 'amount must be numeric'}, status=status.HTTP_400_BAD_REQUEST)

        # build the initial payment request record
        external_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        payment_status = 'pending'
        provider_response = None

        if method == 'ecocash':
            ecocash_url = os.environ.get('ECOCASH_BASE_URL')+"transactions/amount/"
            auth_header = os.environ.get('ECOCASH_AUTH_HEADER')
            if not ecocash_url or not auth_header:
                return Response(
                    {'error': 'EcoCash configuration is missing'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            normalized_phone = normalize_ecocash_phone(phone)
            payload = {
                'clientCorrelator': f'REF-{external_id}',
                'referenceCode': f'INV-{external_id}',
                'tranType': 'MER',
                'endUserId': normalized_phone,
                'paymentAmount': {
                    'chargingInformation': {
                        'amount': f'{float(amount):.2f}',
                        'currency': currency.upper(),
                        'description': 'Online Payment'
                    },
                    'chargeMetaData': {
                        'channel': 'WEB'
                    }
                },
                'merchantCode': os.environ.get('ECOCASH_MERCHANT_CODE'),
                'merchantPin': os.environ.get('ECOCASH_MERCHANT_PIN'),
                'merchantNumber': os.environ.get('ECOCASH_MERCHANT_NUMBER'),
                'countryCode': 'ZW',
                'terminalID': os.environ.get('ECOCASH_TERMINAL_ID'),
                'location': os.environ.get('ECOCASH_LOCATION', 'Harare'),
                'superMerchantName': os.environ.get('ECOCASH_SUPER_MERCHANT_NAME', 'EcoCash Sandbox'),
                'merchantName': os.environ.get('ECOCASH_MERCHANT_NAME', 'Test Merchant'),
                'transactionOperationStatus': 'Charged',
                'remarks': 'Online Payment',
                'notifyUrl': os.environ.get('ECOCASH_NOTIFY_URL', 'https://myapp.example.com/webhook/eip')
            }

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Basic {auth_header}",
            }

            print("[EcoCash Request]")
            print(f"URL: {ecocash_url}")
            print(f"Headers: {headers}")
            print(f"Payload: {json.dumps(payload, indent=2)}")

            try:
                req = Request(ecocash_url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
                with urlopen(req, timeout=30) as response:
                    provider_response = json.loads(response.read().decode('utf-8'))
                    operation_status = provider_response.get('transactionOperationStatus') or provider_response.get('transactionStatus')
                    if operation_status and operation_status.lower() == 'charged':
                        payment_status = 'paid'
            except HTTPError as exc:
                print(f"[HTTPError] Status: {exc.code}")
                try:
                    error_body = exc.read().decode('utf-8')
                    provider_response = json.loads(error_body)
                    print(f"Provider Response: {json.dumps(provider_response, indent=2)}")
                except Exception:
                    provider_response = {'error': str(exc), 'reason': exc.reason}
                    print(f"Could not parse response: {provider_response}")
                return Response(
                    {'error': 'EcoCash request failed', 'details': provider_response},
                    status=status.HTTP_502_BAD_GATEWAY
                )
            except URLError as exc:
                print(f"[URLError] {exc}")
                return Response(
                    {'error': 'EcoCash service unreachable', 'details': str(exc.reason)},
                    status=status.HTTP_502_BAD_GATEWAY
                )


        pr = PaymentRequest.objects.create(
            external_id=external_id,
            method=method,
            phone_number=phone,
            amount=float(amount),
            currency=currency,
            status=payment_status
        )

        response_data = {'external_id': pr.external_id, 'status': pr.status}
        if provider_response is not None:
            response_data['provider_response'] = provider_response

        return Response(response_data, status=status.HTTP_201_CREATED)

class CheckPaymentStatusView(APIView):
    """Check the status of a PaymentRequest"""

    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        external_id = request.query_params.get('external_id')
        if not external_id:
            return Response({'error': 'external_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pr = PaymentRequest.objects.get(external_id=external_id)
        except PaymentRequest.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if pr.method == 'ecocash':
            ecocash_base = os.environ.get('ECOCASH_BASE_URL', 'https://developers.ecocash.co.zw/sandbox')
            auth_header = os.environ.get('ECOCASH_AUTH_HEADER')
            if not auth_header:
                return Response(
                    {'error': 'EcoCash configuration is missing'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            normalized_phone = normalize_ecocash_phone(pr.phone_number)
            status_url = f"{ecocash_base}/payment/v1/{normalized_phone}/transactions/amount/{pr.external_id}"
            headers = {
                'Authorization': auth_header,
            }

            try:
                req = Request(status_url, headers=headers, method='GET')
                with urlopen(req, timeout=30) as response:
                    provider_response = json.loads(response.read().decode('utf-8'))
                    operation_status = provider_response.get('transactionOperationStatus') or provider_response.get('transactionStatus')
                    if operation_status and operation_status.lower() == 'charged':
                        pr.status = 'paid'
                        pr.save(update_fields=['status'])
                    return Response(
                        {
                            'external_id': pr.external_id,
                            'status': pr.status,
                            'provider_response': provider_response,
                        },
                        status=status.HTTP_200_OK,
                    )
            except HTTPError as exc:
                try:
                    error_body = exc.read().decode('utf-8')
                    provider_response = json.loads(error_body)
                except Exception:
                    provider_response = {'error': str(exc)}
                return Response(
                    {'error': 'EcoCash status check failed', 'details': provider_response},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            except URLError as exc:
                return Response(
                    {'error': 'EcoCash service unreachable', 'details': str(exc.reason)},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        return Response({'external_id': pr.external_id, 'status': pr.status}, status=status.HTTP_200_OK)

class DispatchPackageView(APIView):
    """
    Dispatch package workflow
    
    GET: Look up package by receiver code and return details
    POST: Mark package as collected/dispatched
    """
    
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        """
        Search for package by receiver code and retrieve details
        
        Query params: receiver_code
        Returns: receiver_name, package_code, sender_phone, receiver_phone, is_pay_forward, amounts, payment method/currency
        """
        receiver_code = request.query_params.get("receiver_code")
        
        if not receiver_code:
            return Response(
                {"error": "receiver_code is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            package = Package.objects.get(receiver_code=receiver_code)
        except Package.DoesNotExist:
            return Response(
                {"error": "Package not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        pre_package = package.pre_package
        sender_contact = Contact.objects.get(user=pre_package.sender.user)
        receiver_contact = Contact.objects.get(user=pre_package.receiver.user)
        
        response = {
            "receiver_name": f"{pre_package.receiver.user.first_name} {pre_package.receiver.user.last_name}",
            "package_code": pre_package.creation_code,
            "sender_phone": sender_contact.phone_number,
            "receiver_phone": receiver_contact.phone_number,
            "is_pay_forward": package.payment.is_pay_forward,
            "amount_usd": package.payment.amount,
            "amount_zwl": (math.ceil(ExchangeRate.objects.all().last().convert_usd_to_zwl(package.payment.amount)) if ExchangeRate.objects.all().last() else None),
            "payment_method": package.payment.payment_method,
            "currency": package.payment.currency,
        }
        
        return Response(response, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Mark package as collected/dispatched
        
        Required fields:
        - receiver_code: The OTP code printed on the package label
        """
        data = request.data
        receiver_code = data.get("receiver_code")
        
        if not receiver_code:
            return Response(
                {"error": "receiver_code is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            package = Package.objects.get(receiver_code=receiver_code)
        except Package.DoesNotExist:
            return Response(
                {"error": "Package not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Mark package as collected
        from django.utils import timezone
        package.is_collected = True
        package.collected_at = timezone.now()
        package.save()
        
        response = {
            "message": "Package collected successfully",
            "package_id": package.id,
            "package_name": f"{package.batch.id:04}-{package.id:04}",
            "receiver_code": receiver_code,
        }
        return Response(response, status=status.HTTP_200_OK)

class BatchListView(APIView):
    """List all batches for the staff member's branch"""
    
    permission_classes = [IsAuthenticated, IsStaff]
    
    def get(self, request):
        """Get all batches sent from or to the staff member's branch"""
        try:
            staff = Staff.objects.get(user=request.user)
            branch = staff.branch
        except Staff.DoesNotExist:
            return Response(
                {"error": "Staff profile not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get batches where this branch is sender or receiver
        batches = Batch.objects.filter(
            models.Q(sent_from_shop=branch) | models.Q(sent_to_shop=branch)
        ).order_by('-added_at')
        
        batch_list = []
        for batch in batches:
            package_count = Package.objects.filter(batch=batch).count()
            batch_list.append({
                "id": batch.id,
                "sent_from": batch.sent_from_shop.name,
                "sent_from_id": batch.sent_from_shop.id,
                "sent_to": batch.sent_to_shop.name,
                "sent_to_id": batch.sent_to_shop.id,
                "is_available": batch.is_available,
                "added_at": batch.added_at.isoformat(),
                "package_count": package_count,
            })
        
        return Response(batch_list, status=status.HTTP_200_OK)

class BatchDetailView(APIView):
    """Get batch details and list all packages in the batch"""
    
    permission_classes = [IsAuthenticated, IsStaff]
    
    def get(self, request, batch_id):
        """Get batch details and all packages in it"""
        try:
            batch = Batch.objects.get(id=batch_id)
        except Batch.DoesNotExist:
            return Response(
                {"error": "Batch not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Fetch all packages in this batch
        packages = Package.objects.filter(batch=batch).select_related('pre_package', 'payment', 'dimensions')
        
        package_list = []
        for pkg in packages:
            pre_pkg = pkg.pre_package
            sender_contact = Contact.objects.get(user=pre_pkg.sender.user)
            receiver_contact = Contact.objects.get(user=pre_pkg.receiver.user)
            
            exchange_rate = ExchangeRate.objects.all().last()
            amount_zwl = math.ceil(exchange_rate.convert_usd_to_zwl(pkg.payment.amount)) if exchange_rate else None
            
            package_list.append({
                "id": pkg.id,
                "package_code": f"{batch.id:04}-{pkg.id:04}",
                "receiver_code": pkg.receiver_code,
                "creation_code": pre_pkg.creation_code,
                "sender_name": f"{pre_pkg.sender.user.first_name} {pre_pkg.sender.user.last_name}",
                "sender_phone": sender_contact.phone_number,
                "receiver_name": f"{pre_pkg.receiver.user.first_name} {pre_pkg.receiver.user.last_name}",
                "receiver_phone": receiver_contact.phone_number,
                "amount_usd": pkg.payment.amount,
                "amount_zwl": amount_zwl,
                "payment_method": pkg.payment.payment_method,
                "currency": pkg.payment.currency,
                "is_collected": pkg.is_collected,
                "collected_at": pkg.collected_at.isoformat() if pkg.collected_at else None,
                "description": pkg.description,
                "size": pkg.dimensions.get_size() if pkg.dimensions else None,
            })
        
        batch_detail = {
            "id": batch.id,
            "sent_from": batch.sent_from_shop.name,
            "sent_from_id": batch.sent_from_shop.id,
            "sent_to": batch.sent_to_shop.name,
            "sent_to_id": batch.sent_to_shop.id,
            "is_available": batch.is_available,
            "added_at": batch.added_at.isoformat(),
            "package_count": len(package_list),
            "packages": package_list,
        }
        
        return Response(batch_detail, status=status.HTTP_200_OK)

