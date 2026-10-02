from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.users.permissions import IsStaff
from datetime import datetime
from apps.users.models import Biker, Contact, NextOfKin, ProfileImage, Identification, Licence, Branch
from apps.bookkeeping.models import Account, AccountBalance, ExpenseAccount, IntracitySale, Expense, Charge, FundsTransfer, Receipt
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q
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
        intracity_sales = IntracitySale.objects.filter(account=account)
        expenses = Expense.objects.filter(account=account)
        funds_transfers = FundsTransfer.objects.filter((Q(from_account=account) | Q(to_account=account)))
        charges = Charge.objects.filter(account=account)

        if start_date and end_date:
            intracity_sales = intracity_sales.filter(added_at__date__range=[start_date, end_date])
            funds_transfers = funds_transfers.filter(added_at__date__range=[start_date, end_date])
            charges = charges.filter(added_at__date__range=[start_date, end_date])
            expenses = expenses.filter(added_at__date__range=[start_date, end_date])
            
        context = {
            "account_details":{
                "account_id": account.id,
                "account_name": account.name,
                "branch": account.branch.name if account.branch else None,
                "owner": account.owner.username if account.owner else None,
                "currency": account.currency,
                "description": account.description,
                "number": account.number,
                "current_balance": account.get_balance(at_date=end_date),
            },
            "transactions": [{
                "type": "Sales",
                "id": transaction.id,
                "amount": transaction.amount,
                "balance": transaction.running_balance.running_balance if transaction.running_balance else 0,
                "description": transaction.description,
                "date": transaction.added_at,
                "transaction_type": "credit"
            } for transaction in intracity_sales] + [{
                "type": "Expense",
                "id": transaction.id,
                "amount": transaction.amount,
                "balance": transaction.running_balance.running_balance if transaction.running_balance else 0,
                "description": transaction.description,
                "date": transaction.added_at,
                "transaction_type": "debit"
            } for transaction in expenses] + [{
                "type": "Funds Transfer",
                "id": transaction.id,
                "amount": transaction.amount,
                #funds transfer does not have running_balance. there is to_account_running_balance and from_account_running_balance. fix if needed
                "balance": transaction.from_account_running_balance.running_balance if account == transaction.from_account else transaction.to_account_running_balance.running_balance,
                "description": transaction.description,
                "date": transaction.added_at,
                "transaction_type": "debit" if account == transaction.from_account else "credit"
            } for transaction in funds_transfers] + [{
                "type": "Charge",
                "id": transaction.id,
                "amount": transaction.amount,
                "balance": transaction.running_balance.running_balance if transaction.running_balance else 0,
                "description": transaction.description,
                "date": transaction.added_at,
                "transaction_type": "debit"
            } for transaction in charges]
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

        account = Account.objects.get(id=account_id)
        expense_type = ExpenseAccount.objects.get(id=expense_type_id)

        expense = Expense.objects.create(
            account=account,
            expense_type=expense_type,
            amount=amount,
            description=description,
            supplier=supplier,
            added_by=request.user
        )
        if image:
            Receipt.objects.create(
                expense=expense,
                image=image
            )

        context = {
            "success": "Expense created successfully",
            "expense_id": expense.id
        }
        return Response(context, status=status.HTTP_200_OK)

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