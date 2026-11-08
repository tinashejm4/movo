from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework import serializers
from apps.users.permissions import IsStaff
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from apps.users.models import Biker, Contact, NextOfKin, ProfileImage, Identification, Licence, Branch
from apps.bookkeeping.models import Account, ExpenseAccount, IntracitySale, Expense, Charge, FundsTransfer, LedgerEntry, Receipt
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.http import FileResponse
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.utils import timezone
from apps.users.utils import is_valid_zimbabwean_number,normalize_zimbabwean_number

class AccountsListView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        accounts = Account.objects.all()
        context = {
            "accounts_count": accounts.count(),
            "accounts": [{
                "id": account.id,
                "name": account.name,
                "branch": account.branch.name if account.branch else None,
                "currency": account.currency,
                "balance": account.get_balance(),
                "number": account.number,
            } for account in accounts]
        }
        return Response(
            {
                "accounts": context["accounts"],
                "accounts_count": context["accounts_count"]
            },
            status=status.HTTP_200_OK)

class AccountTransactionsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request, account_id):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if start_date and end_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        account = get_object_or_404(Account, id=account_id)
        transactions = LedgerEntry.objects.filter(account=account).select_related(
            "intracity_sale", "expense", "charge", "transfer_out", "transfer_in"
        )

        if start_date and end_date:
            transactions = transactions.filter(actual_date__date__range=[start_date, end_date])
            
        context = {
            "account_details":{
                "account_id": account.id,
                "account_name": account.name,
                "branch": account.branch.name if account.branch else None,
                "owner": account.owner.username if account.owner else None,
                "currency": account.currency,
                "description": account.description,
                "number": account.number,
                "current_balance": account.get_balance(),
            },
            "transactions": [{
                "entry_type": transaction.entry_type,
                "id": transaction.id,
                "amount": transaction.amount,
                "balance": transaction.running_balance,
                "description": transaction.description,
                "date": transaction.actual_date,
                "transaction_type": transaction.transaction_type
            } for transaction in transactions]
        }
        return Response(
            context,
            status=status.HTTP_200_OK)

class ExpenseClassView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        expense_classes = ExpenseAccount.objects.all()
        context = {
            "expense_classes": [{
                "id": expense_class.id,
                "name": expense_class.name,
                "description": expense_class.description,
                "added_at": expense_class.added_at,
            } for expense_class in expense_classes]
        }
        return Response(context, status=status.HTTP_200_OK)

class CreateExpenseView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request):
        account_id = request.data.get("account_id")
        expense_type_id = request.data.get("expense_type_id")
        amount = request.data.get("amount")
        description = request.data.get("description", "")
        supplier = request.data.get("supplier", "")
        image = request.data.get("image")

        try:
            expense_amount = Decimal(str(amount))
            if not expense_amount.is_finite() or expense_amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            return Response({"error": "Amount must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

        account = get_object_or_404(Account, id=account_id)
        expense_type = get_object_or_404(ExpenseAccount, id=expense_type_id)

        with transaction.atomic():
            expense = Expense.objects.create(
                account=account,
                expense_type=expense_type,
                amount=expense_amount,
                description=description,
                supplier=supplier,
                added_by=request.user
            )
            if image:
                Receipt.objects.create(expense=expense, image=image)

        context = {
            "success": "Expense created successfully",
            "expense_id": expense.id
        }
        return Response(context, status=status.HTTP_200_OK)

class BulkExpensesView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request, account_id):
        records = request.data
        if not isinstance(records, list) or not 1 <= len(records) <= 1000:
            return Response({"error": "Provide a JSON array containing 1 to 1000 expenses."}, status=status.HTTP_400_BAD_REQUEST)

        parsed = []
        seen_ids = set()
        for index, record in enumerate(records, 1):
            try:
                if not isinstance(record, dict):
                    raise ValueError("Each expense must be an object.")
                fields = {str(key).strip().lower(): value for key, value in record.items()}
                raw_id = fields.get("id")
                if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
                    raise ValueError("id must be a non-empty string or integer.")
                import_id = str(raw_id).strip()
                if not import_id or len(import_id) > 100:
                    raise ValueError("id must contain between 1 and 100 characters.")
                if import_id in seen_ids:
                    raise ValueError("Duplicate id in the file.")
                seen_ids.add(import_id)
                raw_date = fields.get("date")
                if not isinstance(raw_date, str):
                    raise ValueError("date must use D/M/YYYY format.")
                try:
                    day = datetime.strptime(raw_date.strip(), "%d/%m/%Y").date()
                except ValueError:
                    raise ValueError("date must use D/M/YYYY format.") from None
                if day > timezone.localdate():
                    raise ValueError("Future expense dates are not supported.")
                expense_type = fields.get("type")
                supplier = fields.get("supplier")
                description = fields.get("description", "")
                if not isinstance(expense_type, str) or not expense_type.strip() or len(expense_type.strip()) > 50:
                    raise ValueError("type must contain between 1 and 50 characters.")
                if not isinstance(supplier, str) or not supplier.strip() or len(supplier.strip()) > 100:
                    raise ValueError("supplier must contain between 1 and 100 characters.")
                if not isinstance(description, str):
                    raise ValueError("description must be a string.")
                raw_amount = fields.get("amount")
                if isinstance(raw_amount, bool):
                    raise ValueError("amount must be a positive number with at most two decimal places.")
                try:
                    amount = Decimal(str(raw_amount))
                    if not amount.is_finite() or amount <= 0 or amount > Decimal("9999999999.99") or amount != amount.quantize(Decimal("0.01")):
                        raise ValueError
                except (InvalidOperation, ValueError):
                    raise ValueError("amount must be a positive number with at most two decimal places.") from None
                parsed.append((import_id, day, expense_type.strip(), supplier.strip(), description.strip(), amount))
            except ValueError as error:
                return Response({"error": f"Expense {index}: {error}"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                account = get_object_or_404(Account.objects.select_for_update(), pk=account_id)
                existing = Expense.objects.filter(import_id__in=seen_ids).values_list("import_id", flat=True).first()
                if existing is not None:
                    return Response({"error": f"Expense id '{existing}' has already been imported. No expenses were added."}, status=status.HTTP_409_CONFLICT)
                for import_id, day, type_name, supplier, description, amount in parsed:
                    expense_type = ExpenseAccount.objects.filter(name__iexact=type_name).order_by("id").first()
                    if expense_type is None:
                        expense_type = ExpenseAccount.objects.create(name=type_name)
                    expense = Expense.objects.create(
                        account=account, expense_type=expense_type, amount=amount,
                        supplier=supplier, description=description, added_by=request.user, import_id=import_id,
                    )
                    actual_date = timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())
                    Expense.objects.filter(pk=expense.pk).update(actual_date=actual_date)
                    LedgerEntry.objects.filter(pk=expense.ledger_entry_id).update(actual_date=actual_date)

                balance = Decimal("0.00")
                for entry in LedgerEntry.objects.filter(account=account).order_by("actual_date", "pk").iterator():
                    balance += entry.amount
                    LedgerEntry.objects.filter(pk=entry.pk).update(running_balance=balance)
        except IntegrityError:
            return Response({"error": "An expense ID was already imported or a database constraint failed. No expenses were added."}, status=status.HTTP_409_CONFLICT)
        return Response({"imported": len(parsed)}, status=status.HTTP_201_CREATED)

class ListExpensesView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request, account_id):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        if bool(start_date) != bool(end_date):
            return Response({"error": "Provide both start and end dates."}, status=status.HTTP_400_BAD_REQUEST)
        if start_date and end_date:
            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                return Response({"error": "Dates must use YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST)
            if start_date > end_date:
                return Response({"error": "Start date must not be after end date."}, status=status.HTTP_400_BAD_REQUEST)
        account = get_object_or_404(Account, id=account_id)
        expenses = Expense.objects.filter(account=account).select_related(
            "account", "expense_type", "added_by", "receipt"
        ).order_by("-actual_date", "-id")
        if start_date and end_date:
            expenses = expenses.filter(actual_date__date__range=[start_date, end_date])
        expenses_data = [{
            "id": expense.id,
            "account": expense.account.name if expense.account else None,
            "expense_type": expense.expense_type.name if expense.expense_type else None,
            "amount": expense.amount,
            "description": expense.description,
            "supplier": expense.supplier,
            "has_image": hasattr(expense, "receipt"),
            "added_by": expense.added_by.username if expense.added_by else None,
            "added_at": expense.added_at,
            "actual_date": expense.actual_date,
        } for expense in expenses]
        return Response({"expenses": expenses_data}, status=status.HTTP_200_OK)

class CreateChargeView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]
    def post(self, request):
        account_id = request.data.get("account_id")
        amount = request.data.get("amount")
        description = request.data.get("description", "")

        account = Account.objects.get(id=account_id)

        charge = Charge.objects.create(
            account=account,
            amount=amount,
            description=description,
            added_by=request.user
        )

        context = {
            "success": "Charge created successfully",
            "charge_id": charge.id
        }
        return Response(context, status=status.HTTP_200_OK)

class CreateFundsTransferView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]
    def post(self, request):
        from_account_id = request.data.get("from_account_id")
        to_account_id = request.data.get("to_account_id")
        amount = request.data.get("amount")
        description = request.data.get("description", "")

        from_account = Account.objects.get(id=from_account_id)
        to_account = Account.objects.get(id=to_account_id)

        if float(amount) <= 0:
            return Response({"error": "Transfer amount must be greater than zero"}, status=status.HTTP_400_BAD_REQUEST)

        if from_account.get_balance() < float(amount):
            return Response({"error": "Insufficient funds in the source account"}, status=status.HTTP_400_BAD_REQUEST)

        if from_account == to_account:
            return Response({"error": "Cannot transfer funds to the same account"}, status=status.HTTP_400_BAD_REQUEST)

        transfer = FundsTransfer.objects.create(
            from_account=from_account,
            to_account=to_account,
            amount=amount,
            description=description,
            initiated_by=request.user
        )

        context = {
            "success": "Funds transfer created successfully",
            "transfer_id": transfer.id
        }
        return Response(context, status=status.HTTP_200_OK)

class ReceiptImageView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]
    def post(self, request):
        expense_id = request.data.get("expense_id")
        try:
            expense = Expense.objects.get(id=expense_id)
        except Expense.DoesNotExist:
            return Response({"error": "Expense not found"}, status=status.HTTP_404_NOT_FOUND)

        image = Receipt.objects.get(expense=expense).image if Receipt.objects.filter(expense=expense).exists() else None
        if not image:
            return Response({"error": "Image not found"}, status=status.HTTP_400_BAD_REQUEST)

        context = {
            "success": "Receipt retrieved successfully", 
            "image": Receipt.objects.get(expense=expense).image.url
            }
        
        return Response(context, status=status.HTTP_200_OK)

class ExpenseReceiptView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request, account_id, expense_id):
        receipt = get_object_or_404(
            Receipt.objects.select_related("expense"),
            expense_id=expense_id,
            expense__account_id=account_id,
        )
        try:
            image = receipt.image.open("rb")
        except FileNotFoundError:
            return Response({"error": "Receipt image file not found."}, status=status.HTTP_404_NOT_FOUND)

        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(image) as decoded:
                content_type = Image.MIME.get(decoded.format)
                decoded.verify()
            if content_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
                image.close()
                return Response({"error": "Unsupported receipt image format."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
            image.seek(0)
        except (UnidentifiedImageError, OSError, ValueError):
            image.close()
            return Response({"error": "Unable to read receipt image."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        response = FileResponse(image, content_type=content_type)
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def post(self, request, account_id, expense_id):
        image = request.FILES.get("image")
        if not image:
            return Response({"error": "Select an image to upload."}, status=status.HTTP_400_BAD_REQUEST)
        if image.size > 10 * 1024 * 1024:
            return Response({"error": "Receipt image must be 10 MB or smaller."}, status=status.HTTP_400_BAD_REQUEST)
        field = serializers.ImageField()
        try:
            image = field.run_validation(image)
        except serializers.ValidationError as error:
            return Response({"error": str(error.detail[0])}, status=status.HTTP_400_BAD_REQUEST)
        if image.image.format not in {"JPEG", "PNG", "GIF", "WEBP"}:
            return Response({"error": "Use a JPEG, PNG, GIF or WebP image."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            expense = get_object_or_404(
                Expense.objects.select_for_update(), id=expense_id, account_id=account_id
            )
            if Receipt.objects.filter(expense=expense).exists():
                return Response({"error": "This expense already has a receipt."}, status=status.HTTP_409_CONFLICT)
            Receipt.objects.create(expense=expense, image=image)
        return Response({"success": "Receipt uploaded successfully."}, status=status.HTTP_201_CREATED)

class ExpenseReversalView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]
    def post(self, request):
        expense_id = request.data.get("expense_id")
        reason = request.data.get("reason", "")

        try:
            expense = Expense.objects.get(id=expense_id)
        except Expense.DoesNotExist:
            return Response({"error": "Expense not found"}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not reason:
            return Response({"error": "Reason for reversal is required"}, status=status.HTTP_400_BAD_REQUEST)

        expense.reverse(user, reason)
        return Response({"success": "Expense reversed successfully"}, status=status.HTTP_200_OK)

class ChargeReversalView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]
    def post(self, request):
        charge_id = request.data.get("charge_id")
        reason = request.data.get("reason", "")

        try:
            charge = Charge.objects.get(id=charge_id)
        except Charge.DoesNotExist:
            return Response({"error": "Charge not found"}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not reason:
            return Response({"error": "Reason for reversal is required"}, status=status.HTTP_400_BAD_REQUEST)

        charge.reverse(user, reason)
        return Response({"success": "Charge reversed successfully"}, status=status.HTTP_200_OK)

class FundsTransferReversalView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]
    def post(self, request):
        transfer_id = request.data.get("transfer_id")
        reason = request.data.get("reason", "")

        try:
            transfer = FundsTransfer.objects.get(id=transfer_id)
        except FundsTransfer.DoesNotExist:
            return Response({"error": "Funds Transfer not found"}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not reason:
            return Response({"error": "Reason for reversal is required"}, status=status.HTTP_400_BAD_REQUEST)

        transfer.reverse(user, reason)
        return Response({"success": "Funds Transfer reversed successfully"}, status=status.HTTP_200_OK)