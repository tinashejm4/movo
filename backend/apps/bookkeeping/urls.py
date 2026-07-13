from django.urls import path
from .views import (
    ExpensesView,
    TransportExpensesView,
    FundsTransferView,
    AccountLedgerView,
    AccountsView,
    ExpenseTypesView,
    AvailableBatchesView,
    DailyBranchAccountsView,
    CloseAccountForDayView,
)

urlpatterns = [
    path("accounts/", AccountsView.as_view(), name="accounts"),
    path("accounts/daily-summary/", DailyBranchAccountsView.as_view(), name="daily_branch_accounts"),
    path("accounts/close-day/", CloseAccountForDayView.as_view(), name="close_account_for_day"),
    path("expense-types/", ExpenseTypesView.as_view(), name="expense_types"),
    path("available-batches/", AvailableBatchesView.as_view(), name="available_batches"),
    path("expenses/", ExpensesView.as_view(), name="expenses"),
    path("transport-expenses/", TransportExpensesView.as_view(), name="transport_expenses"),
    path("transfers/", FundsTransferView.as_view(), name="funds_transfers"),
    path("accounts/ledger/", AccountLedgerView.as_view(), name="account_ledger"),
]
