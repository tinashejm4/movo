import datetime
from django.core.exceptions import FieldError
from django.db.models import Q, Sum
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsStaff
from users.models import Staff
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from intercity.models import Batch
from .models import InterCitySale, Account, Charge, EndOfDayBalance, Expense, ExpenseType, FundsTransfer,  TransportExpense


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    return amount


def _get_transport_batch_field_name():
    # The model currently defines the FK as `Batch`; keep this resilient.
    if hasattr(TransportExpense, "Batch"):
        return "Batch"
    return "batch"


def _get_staff_branch(user):
    try:
        print("get staff branch", Staff.objects.get(user = user).branch)
        return Staff.objects.get(user = user).branch
    except Staff.DoesNotExist:
        return None


def _branch_expenses_qs(branch):
    """Support both legacy and corrected Expense.account relationships."""
    try:
        return Expense.objects.select_related("expense_type", "added_by").filter(account__branch=branch)
    except FieldError:
        return Expense.objects.select_related("expense_type", "added_by").filter(account__sent_from_shop=branch)


def _branch_available_batches_qs(branch):
    return Batch.objects.filter(is_available=True).filter(
        Q(sent_from_shop=branch) | Q(sent_to_shop=branch)
    )


def _opening_balance_for_date(account, target_date):
    latest = EndOfDayBalance.objects.filter(
        account=account,
        added_at__lt=target_date,
        accepted=True,
    ).order_by("-added_at", "-id").first()
    if not latest:
        latest = EndOfDayBalance.objects.filter(
            account=account,
            added_at__lt=target_date,
        ).order_by("-added_at", "-id").first()
    return float(latest.actual_balance if latest else 0)


def _daily_account_metrics(account, staff_branch, target_date):
    opening_balance = _opening_balance_for_date(account, target_date)

    day_sales = float(
        # Sale.objects.filter(account=account, added_at=target_date).aggregate(total=Sum("amount"))["total"] or 0
    )
    day_expenses = float(
        _branch_expenses_qs(staff_branch).filter(account_id=account.id, added_at=target_date).aggregate(total=Sum("amount"))["total"] or 0
    )
    day_transport_expenses = float(
        TransportExpense.objects.filter(account=account, added_at=target_date).aggregate(total=Sum("amount"))["total"] or 0
    )
    day_charges = float(
        Charge.objects.filter(account=account, added_at=target_date).aggregate(total=Sum("amount"))["total"] or 0
    )

    day_transfer_in = float(
        FundsTransfer.objects.filter(to_account=account, added_at=target_date).aggregate(total=Sum("amount"))["total"] or 0
    )
    day_transfer_out = float(
        FundsTransfer.objects.filter(from_account=account, added_at=target_date).aggregate(total=Sum("amount"))["total"] or 0
    )

    total_expenditure = day_expenses + day_transport_expenses + day_charges
    current_balance = opening_balance + day_sales + day_transfer_in - total_expenditure - day_transfer_out

    return {
        "opening_balance": opening_balance,
        "total_sales": day_sales,
        "total_expenditure": total_expenditure,
        "current_balance": current_balance,
        "transfer_in": day_transfer_in,
        "transfer_out": day_transfer_out,
    }


class AccountsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        accounts = Account.objects.filter(branch=staff_branch).order_by("name", "id")
        rows = [
            {
                "id": account.id,
                "name": account.name,
                "currency": account.currency,
                "branch_id": account.branch_id,
                "branch_name": account.branch.name if account.branch else None,
            }
            for account in accounts
        ]
        return Response(rows, status=status.HTTP_200_OK)


class DailyBranchAccountsView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        target_date = _parse_date(request.query_params.get("date")) or datetime.date.today()
        accounts = Account.objects.filter(branch=staff_branch).order_by("name", "id")

        rows = []
        for account in accounts:
            metrics = _daily_account_metrics(account, staff_branch, target_date)
            closed_record = EndOfDayBalance.objects.filter(account=account, added_at=target_date).order_by("-id").first()

            rows.append(
                {
                    "account_id": account.id,
                    "account_name": account.name,
                    "currency": account.currency,
                    "date": target_date.isoformat(),
                    "opening_balance": metrics["opening_balance"],
                    "current_balance": metrics["current_balance"],
                    "total_expenditure": metrics["total_expenditure"],
                    "total_sales": metrics["total_sales"],
                    "is_closed_for_day": bool(closed_record),
                    "end_of_day_balance_id": closed_record.id if closed_record else None,
                }
            )

        return Response(rows, status=status.HTTP_200_OK)


class CloseAccountForDayView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        account_id = data.get("account_id")
        target_date = _parse_date(data.get("date")) or datetime.date.today()

        if not account_id:
            return Response({"error": "account_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            account = Account.objects.get(id=account_id, branch=staff_branch)
        except Account.DoesNotExist:
            return Response({"error": "Account not found for your branch"}, status=status.HTTP_404_NOT_FOUND)

        metrics = _daily_account_metrics(account, staff_branch, target_date)
        expected_balance = metrics["current_balance"]
        actual_balance = data.get("actual_balance")
        if actual_balance is None:
            actual_balance = expected_balance
        else:
            try:
                actual_balance = float(actual_balance)
            except (TypeError, ValueError):
                return Response({"error": "actual_balance must be numeric"}, status=status.HTTP_400_BAD_REQUEST)

        closed_record = EndOfDayBalance.objects.filter(account=account, added_at=target_date).order_by("-id").first()
        if closed_record:
            closed_record.expected_balance = expected_balance
            closed_record.actual_balance = actual_balance
            closed_record.accepted = True
            closed_record.accepted_by = request.user
            closed_record.added_by = request.user
            closed_record.save(update_fields=["expected_balance", "actual_balance", "accepted", "accepted_by", "added_by"])
        else:
            closed_record = EndOfDayBalance.objects.create(
                account=account,
                expected_balance=expected_balance,
                actual_balance=actual_balance,
                accepted=True,
                accepted_by=request.user,
                added_by=request.user,
            )

        branch_account_ids = list(Account.objects.filter(branch=staff_branch).values_list("id", flat=True))
        closed_for_day_count = EndOfDayBalance.objects.filter(
            account_id__in=branch_account_ids,
            added_at=target_date,
        ).values("account_id").distinct().count()
        all_closed_for_day = bool(branch_account_ids) and closed_for_day_count == len(branch_account_ids)

        user_locked_out = False
        if all_closed_for_day and request.user.is_active:
            request.user.is_active = False
            request.user.save(update_fields=["is_active"])
            user_locked_out = True

        return Response(
            {
                "message": "Account closed for the day",
                "end_of_day_balance_id": closed_record.id,
                "account_id": account.id,
                "date": target_date.isoformat(),
                "expected_balance": expected_balance,
                "actual_balance": float(actual_balance),
                "all_closed_for_day": all_closed_for_day,
                "user_locked_out": user_locked_out,
            },
            status=status.HTTP_200_OK,
        )


class ExpenseTypesView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        types = ExpenseType.objects.all().order_by("name", "id")
        rows = [{"id": row.id, "name": row.name} for row in types]
        return Response(rows, status=status.HTTP_200_OK)


class AvailableBatchesView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        rows = [
            {
                "id": batch.id,
                "sent_from_id": batch.sent_from_shop_id,
                "sent_from_name": batch.sent_from_shop.name,
                "sent_to_id": batch.sent_to_shop_id,
                "sent_to_name": batch.sent_to_shop.name,
                "is_available": batch.is_available,
                "added_at": batch.added_at.isoformat(),
                "label": f"Batch #{batch.id} - {batch.sent_from_shop.name} to {batch.sent_to_shop.name}",
            }
            for batch in _branch_available_batches_qs(staff_branch).select_related("sent_from_shop", "sent_to_shop").order_by("-added_at")
        ]
        return Response(rows, status=status.HTTP_200_OK)


class ExpensesView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        account_id = data.get("account_id")
        expense_type_id = data.get("expense_type_id")
        amount = _parse_amount(data.get("amount"))
        comment = data.get('comment', '')
        if not account_id or not expense_type_id or amount is None:
            return Response(
                {"error": "account_id, expense_type_id and a positive amount are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account = Account.objects.get(id=account_id)
        except Account.DoesNotExist:
            return Response({"error": "Account not found"}, status=status.HTTP_404_NOT_FOUND)

        if account.branch_id != staff_branch.id:
            return Response(
                {"error": "You can only add expenses to accounts in your branch"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            expense_type = ExpenseType.objects.get(id=expense_type_id)
        except ExpenseType.DoesNotExist:
            return Response({"error": "Expense type not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            expense = Expense.objects.create(
                account=account,
                expense_type=expense_type,
                amount=amount,
                comment=comment,
                added_by=request.user,
            )
        except Exception as exc:
            # Keep error explicit because model relations differ across dev DBs.
            return Response(
                {"error": f"Could not create expense: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = {
            "message": "Expense recorded successfully",
            "expense_id": expense.id,
        }

        return Response(response, status=status.HTTP_201_CREATED)
    
    def get(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        account_id = request.query_params.get("account_id")
        from_date = _parse_date(request.query_params.get("from_date"))
        to_date = _parse_date(request.query_params.get("to_date"))

        expenses = _branch_expenses_qs(staff_branch)
        if account_id:
            expenses = expenses.filter(account_id=account_id)
        if from_date:
            expenses = expenses.filter(added_at__gte=from_date)
        if to_date:
            expenses = expenses.filter(added_at__lte=to_date)

        expenses_list = [
            {
                "id": expense.id,
                "account_id": expense.account_id,
                "expense_type_id": expense.expense_type_id,
                "expense_type": expense.expense_type.name,
                "amount": float(expense.amount),
                "comment": expense.comment,
                "added_by": expense.added_by.username if expense.added_by else None,
                "added_at": expense.added_at.isoformat(),
            }
            for expense in expenses.order_by("-added_at", "-id")
        ]

        return Response(expenses_list, status=status.HTTP_200_OK)

class TransportExpensesView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        account_id = data.get("account_id")
        amount = _parse_amount(data.get("amount"))
        comment = data.get('comment', '')
        batch_id = data.get("batch_id")
        transport_category = (data.get("transport_category") or "").strip()

        if not account_id or not batch_id or amount is None or not transport_category:
            return Response(
                {"error": "account_id, batch_id, transport_category and a positive amount are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account = Account.objects.get(id=account_id)
        except Account.DoesNotExist:
            return Response({"error": "Account not found"}, status=status.HTTP_404_NOT_FOUND)

        if account.branch_id != staff_branch.id:
            return Response(
                {"error": "You can only add transport expenses to accounts in your branch"},
                status=status.HTTP_403_FORBIDDEN,
            )

        expense_type = ExpenseType.objects.filter(id=1).first()
        if not expense_type:
            return Response(
                {"error": "Default transport expense type (id=1) was not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            batch = _branch_available_batches_qs(staff_branch).get(id=batch_id)
        except Batch.DoesNotExist:
            return Response(
                {"error": "Batch not found, unavailable, or outside your branch"},
                status=status.HTTP_404_NOT_FOUND,
            )

        batch_field = _get_transport_batch_field_name()
        transport_kwargs = {
            "account": account,
            "expense_type": expense_type,
            "transport_category": transport_category,
            "amount": amount,
            "comment": comment,
            "added_by": request.user,
            batch_field + "_id": batch.id,
        }

        try:
            transport_expense = TransportExpense.objects.create(**transport_kwargs)
        except Exception as exc:
            return Response(
                {"error": f"Could not create transport expense: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = {
            "message": "Transport expense recorded successfully",
            "transport_expense_id": transport_expense.id,
        }

        return Response(response, status=status.HTTP_201_CREATED)


class FundsTransferView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        from_account_id = data.get("from_account_id")
        to_account_id = data.get("to_account_id")
        amount = _parse_amount(data.get("amount"))
        comment = data.get("comment", "")

        if not from_account_id or not to_account_id or amount is None:
            return Response(
                {"error": "from_account_id, to_account_id and a positive amount are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if str(from_account_id) == str(to_account_id):
            return Response(
                {"error": "from_account_id and to_account_id must be different"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from_account = Account.objects.get(id=from_account_id)
            to_account = Account.objects.get(id=to_account_id)
        except Account.DoesNotExist:
            return Response({"error": "One or both accounts not found"}, status=status.HTTP_404_NOT_FOUND)

        if from_account.branch_id != staff_branch.id or to_account.branch_id != staff_branch.id:
            return Response(
                {"error": "You can only transfer between accounts in your branch"},
                status=status.HTTP_403_FORBIDDEN,
            )

        transfer = FundsTransfer.objects.create(
            from_account=from_account,
            to_account=to_account,
            amount=amount,
            comment=comment,
            added_by=request.user,
        )

        return Response(
            {
                "message": "Transfer recorded successfully",
                "transfer_id": transfer.id,
            },
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        account_id = request.query_params.get("account_id")
        from_date = _parse_date(request.query_params.get("from_date"))
        to_date = _parse_date(request.query_params.get("to_date"))

        transfers = FundsTransfer.objects.select_related("from_account", "to_account", "added_by").filter(
            from_account__branch=staff_branch,
            to_account__branch=staff_branch,
        )
        if account_id:
            transfers = transfers.filter(Q(from_account_id=account_id) | Q(to_account_id=account_id))
        if from_date:
            transfers = transfers.filter(added_at__gte=from_date)
        if to_date:
            transfers = transfers.filter(added_at__lte=to_date)

        rows = []
        for transfer in transfers.order_by("-added_at", "-id"):
            direction = "out"
            if account_id and str(transfer.to_account_id) == str(account_id):
                direction = "in"
            rows.append(
                {
                    "id": transfer.id,
                    "from_account_id": transfer.from_account_id,
                    "from_account": transfer.from_account.name,
                    "to_account_id": transfer.to_account_id,
                    "to_account": transfer.to_account.name,
                    "amount": float(transfer.amount),
                    "direction": direction,
                    "comment": transfer.comment,
                    "added_by": transfer.added_by.username if transfer.added_by else None,
                    "added_at": transfer.added_at.isoformat(),
                }
            )

        return Response(rows, status=status.HTTP_200_OK)


class AccountLedgerView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        staff_branch = _get_staff_branch(request.user)
        if not staff_branch:
            return Response({"error": "Staff branch not found"}, status=status.HTTP_403_FORBIDDEN)

        account_id = request.query_params.get("account_id")
        from_date = _parse_date(request.query_params.get("from_date"))
        to_date = _parse_date(request.query_params.get("to_date"))

        accounts = Account.objects.filter(branch=staff_branch)
        if account_id:
            accounts = accounts.filter(id=account_id)

        response = []
        for account in accounts:
            sales = InterCitySale.objects.filter(account=account)
            expenses = _branch_expenses_qs(staff_branch).filter(account_id=account.id)
            transport_expenses = TransportExpense.objects.filter(account=account)
            incoming = FundsTransfer.objects.filter(to_account=account)
            outgoing = FundsTransfer.objects.filter(from_account=account)

            if from_date:
                sales = sales.filter(added_at__gte=from_date)
                expenses = expenses.filter(added_at__gte=from_date)
                transport_expenses = transport_expenses.filter(added_at__gte=from_date)
                incoming = incoming.filter(added_at__gte=from_date)
                outgoing = outgoing.filter(added_at__gte=from_date)
            if to_date:
                sales = sales.filter(added_at__lte=to_date)
                expenses = expenses.filter(added_at__lte=to_date)
                transport_expenses = transport_expenses.filter(added_at__lte=to_date)
                incoming = incoming.filter(added_at__lte=to_date)
                outgoing = outgoing.filter(added_at__lte=to_date)

            total_sales = float(sales.aggregate(total=Sum("amount"))["total"] or 0)
            total_expenses = float(expenses.aggregate(total=Sum("amount"))["total"] or 0)
            total_transport_expenses = float(transport_expenses.aggregate(total=Sum("amount"))["total"] or 0)
            total_incoming = float(incoming.aggregate(total=Sum("amount"))["total"] or 0)
            total_outgoing = float(outgoing.aggregate(total=Sum("amount"))["total"] or 0)

            entries = []
            for sale in sales:
                entries.append(
                    {
                        "id": sale.id,
                        "type": "sale",
                        "direction": "in",
                        "amount": float(sale.amount),
                        "comment": "Package sale",
                        "added_at": sale.added_at.isoformat(),
                    }
                )

            for expense in expenses.select_related("expense_type"):
                entries.append(
                    {
                        "id": expense.id,
                        "type": "expense",
                        "direction": "out",
                        "amount": float(expense.amount),
                        "comment": expense.comment,
                        "expense_type": expense.expense_type.name,
                        "added_at": expense.added_at.isoformat(),
                    }
                )

            for expense in transport_expenses.select_related("expense_type"):
                entries.append(
                    {
                        "id": expense.id,
                        "type": "transport_expense",
                        "direction": "out",
                        "amount": float(expense.amount),
                        "comment": expense.comment,
                        "expense_type": expense.expense_type.name,
                        "added_at": expense.added_at.isoformat(),
                    }
                )

            for transfer in incoming.select_related("from_account"):
                entries.append(
                    {
                        "id": transfer.id,
                        "type": "transfer",
                        "direction": "in",
                        "amount": float(transfer.amount),
                        "comment": transfer.comment,
                        "counterparty_account": transfer.from_account.name,
                        "added_at": transfer.added_at.isoformat(),
                    }
                )

            for transfer in outgoing.select_related("to_account"):
                entries.append(
                    {
                        "id": transfer.id,
                        "type": "transfer",
                        "direction": "out",
                        "amount": float(transfer.amount),
                        "comment": transfer.comment,
                        "counterparty_account": transfer.to_account.name,
                        "added_at": transfer.added_at.isoformat(),
                    }
                )

            entries.sort(key=lambda row: (row["added_at"], row["id"]), reverse=True)

            response.append(
                {
                    "account_id": account.id,
                    "account_name": account.name,
                    "currency": account.currency,
                    "branch_id": account.branch_id,
                    "branch_name": account.branch.name if account.branch else None,
                    "totals": {
                        "sales": total_sales,
                        "expenses": total_expenses,
                        "transport_expenses": total_transport_expenses,
                        "all_expenses": total_expenses + total_transport_expenses,
                        "transfer_in": total_incoming,
                        "transfer_out": total_outgoing,
                        "net": total_sales + total_incoming - (total_expenses + total_transport_expenses) - total_outgoing,
                    },
                    "entries": entries,
                }
            )

        return Response(response, status=status.HTTP_200_OK)


