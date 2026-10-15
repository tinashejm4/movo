from decimal import Decimal
import uuid

from django.test import TestCase

from .models import (
    Account,
    Charge,
    Expense,
    ExpenseAccount,
    FundsTransfer,
    IntracitySale,
    LedgerEntry,
)


class IntracitySaleLedgerTests(TestCase):
    def setUp(self):
        self.account = Account.objects.create(name="Intracity sales")
        self.expense_type = ExpenseAccount.objects.create(name="Supplies")

    def test_creating_sale_creates_its_ledger_entry(self):
        sale = IntracitySale.objects.create(account=self.account, amount=12.5)

        sale.refresh_from_db()
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(sale.ledger_entry.account, self.account)
        self.assertEqual(sale.ledger_entry.amount, Decimal("12.50"))
        self.assertEqual(sale.ledger_entry.running_balance, Decimal("12.50"))
        self.assertEqual(sale.ledger_entry.transaction_type, "sale")

    def test_saving_existing_sale_does_not_create_a_second_ledger_entry(self):
        sale = IntracitySale.objects.create(account=self.account, amount=12.5)

        sale.description = "Updated description"
        sale.save()

        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(sale.ledger_entry.running_balance, Decimal("12.50"))

    def test_get_balance_uses_decimal_and_debits_reduce_the_balance(self):
        credit = LedgerEntry.objects.create(
            account=self.account,
            entry_type=LedgerEntry.CREDIT,
            amount=Decimal("20.00"),
            running_balance=Decimal("0.00"),
            transaction_type="sale",
            reference=uuid.uuid4(),
        )
        debit = LedgerEntry.objects.create(
            account=self.account,
            entry_type=LedgerEntry.DEBIT,
            amount=Decimal("5.00"),
            running_balance=Decimal("0.00"),
            transaction_type="expense",
            reference=uuid.uuid4(),
        )

        self.assertEqual(credit.running_balance, Decimal("20.00"))
        self.assertEqual(debit.amount, Decimal("-5.00"))
        self.assertEqual(debit.running_balance, Decimal("15.00"))
        self.assertEqual(self.account.get_balance(), Decimal("15.00"))

    def test_expense_and_charge_create_debit_entries(self):
        expense = Expense.objects.create(
            account=self.account,
            amount=3.25,
            expense_type=self.expense_type,
        )
        charge = Charge.objects.create(account=self.account, amount=1.25)

        self.assertEqual(expense.ledger_entry.amount, Decimal("-3.25"))
        self.assertEqual(charge.ledger_entry.amount, Decimal("-1.25"))
        self.assertEqual(charge.ledger_entry.running_balance, Decimal("-4.50"))
        self.assertIsNotNone(expense.running_balance)
        self.assertIsNotNone(charge.running_balance)

    def test_transfer_creates_balanced_entries_on_both_accounts(self):
        source = Account.objects.create(name="Source")
        target = Account.objects.create(name="Target")
        IntracitySale.objects.create(account=source, amount=30)

        transfer = FundsTransfer.objects.create(
            from_account=source,
            to_account=target,
            amount=12,
        )

        self.assertEqual(
            transfer.from_account_ledger_entry.amount, Decimal("-12.00")
        )
        self.assertEqual(
            transfer.to_account_ledger_entry.amount, Decimal("12.00")
        )
        self.assertEqual(source.get_balance(), Decimal("18.00"))
        self.assertEqual(target.get_balance(), Decimal("12.00"))
        self.assertEqual(
            transfer.from_account_ledger_entry.reference,
            transfer.to_account_ledger_entry.reference,
        )
