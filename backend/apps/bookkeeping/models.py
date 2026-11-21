from datetime import datetime, timezone
from django.utils import timezone
from decimal import Decimal
import uuid

from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.utils import timezone
from apps.users.models import Branch
from django.contrib.auth.models import User


class Account(models.Model):
    CURRENCY_CHOICES = [
        ("USD", "US Dollar"),
        ("EUR", "Euro"),
        ("ZWL", "Zimbabwean Dollar"),
        ("RAN", "South African Rand"),
    ]

    name = models.CharField(max_length = 50)
    branch = models.ForeignKey(Branch, on_delete = models.CASCADE, blank = True, null = True)
    owner = models.ForeignKey(User, on_delete = models.SET_NULL, null = True, blank = True)
    currency = models.CharField(max_length = 10, choices=CURRENCY_CHOICES, default = "USD")
    description = models.TextField(blank = True, null = True)
    number = models.CharField(max_length = 20, blank = True, null = True)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"{self.name} - {self.number}"

    def get_balance(self, at_datetime=None):
        entries = LedgerEntry.objects.filter(account=self)
        if at_datetime:
            entries = entries.filter(actual_date__lte=at_datetime)
        balance = entries.order_by("-actual_date", "-pk").first()
        if balance:
            return Decimal(balance.running_balance)
        if at_datetime:
            legacy_balance = LedgerEntry.objects.filter(account=self).filter(actual_date__lte=at_datetime)
        else:
            legacy_balance = LedgerEntry.objects.filter(account=self)
        legacy_balance = legacy_balance.order_by("-actual_date", "-pk").first()
        return (
            Decimal(legacy_balance.running_balance)
            if legacy_balance
            else Decimal("0.00")
        )

class LedgerEntry(models.Model):
    CREDIT = "credit"
    DEBIT = "debit"

    ENTRY_TYPES = [
        (CREDIT, "Credit"),
        (DEBIT, "Debit"),
    ]

    TRANSACTION_TYPES = [
        ("sale", "Sale"),
        ("expense", "Expense"),
        ("transfer in", "Transfer In"),
        ("transfer out", "Transfer Out"),
        ("charge", "Charge"),
        ("capital infusion", "Capital Infusion"),
    ]

    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    entry_type = models.CharField(max_length=10,choices=ENTRY_TYPES)
    amount = models.DecimalField(max_digits=12,decimal_places=2)
    running_balance = models.DecimalField(max_digits=12,decimal_places=2)
    actual_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    transaction_type = models.CharField(max_length=255, choices=TRANSACTION_TYPES)
    reference = models.UUIDField()

    def __str__(self):
        return f"{self.account} - {self.entry_type} - {self.amount}"

    @classmethod
    def recalculate_account_balances(cls, account_id):
        balance = Decimal("0.00")
        entries = cls.objects.filter(account_id=account_id).order_by("actual_date", "pk")
        for entry in entries.iterator():
            balance += entry.amount
            if entry.running_balance != balance:
                cls.objects.filter(pk=entry.pk).update(running_balance=balance)

    @property
    def source(self):
        """The child record (sale, expense, charge or transfer) behind this entry."""
        for name in ("intracity_sale", "expense", "charge", "transfer_out", "transfer_in"):
            try:
                return getattr(self, name)
            except ObjectDoesNotExist:
                continue
        return None

    @property
    def description(self):
        source = self.source
        return getattr(source, "description", None) if source else None

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.actual_date:
            self.actual_date = timezone.now()
        amount = round(abs(Decimal(str(self.amount))), 2)
        if self.entry_type == self.DEBIT:
            amount = -amount
        elif self.entry_type != self.CREDIT:
            raise ValueError(f"Unsupported ledger entry type: {self.entry_type}")
        self.amount = Decimal(amount)

        if self._state.adding:
            account = Account.objects.select_for_update().get(pk=self.account_id)
            self.running_balance = account.get_balance() + Decimal(self.amount)

        super().save(*args, **kwargs)

class IntracitySale(models.Model):
    ledger_entry = models.OneToOneField(
        LedgerEntry,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="intracity_sale",
    )
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    invoice = models.OneToOneField('intracity.Invoice', on_delete=models.CASCADE, null=True, blank=True)
    description = models.TextField(blank = True, null = True)
    amount = models.FloatField(default=0)
    added_at = models.DateTimeField(auto_now_add = True)

    def __str__(self):
        return f"{self.ledger_entry.account} -{self.invoice}- {self.ledger_entry.amount}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.ledger_entry_id:
            self.account = self.ledger_entry.account
            self.amount = Decimal(self.ledger_entry.amount)
        else:
            if not self.account_id:
                raise ValueError("An account is required to record an intracity sale.")
            amount = round(abs(Decimal(str(self.amount))), 2)
            if not amount and self.invoice_id:
                amount = round(abs(Decimal(str(self.invoice.amount))), 2)
            self.ledger_entry = LedgerEntry.objects.create(
                account=self.account,
                entry_type=LedgerEntry.CREDIT,
                amount=amount,
                running_balance=Decimal("0.00"),
                transaction_type="sale",
                reference=uuid.uuid4(),
            )
            self.amount = Decimal(self.ledger_entry.amount)

        if not self.description and self.invoice_id:
            self.description = self.invoice.package.slug

        super().save(*args, **kwargs)

class Asset(models.Model):
    ASSET_TYPES = [
        ('vehicle', 'Vehicle'),
        ('equipment', 'Equipment'),
        ('furniture', 'Furniture'),
        ('other', 'Other')
    ]

    asset_type = models.CharField(max_length=50, choices=ASSET_TYPES)
    name = models.CharField(max_length=100)
    supplier = models.CharField(max_length=100, blank=True, null=True)
    unique_identifier = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}"

class AssetImage(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='asset_images/')
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for Asset {self.asset}"


class ExpenseAccount(models.Model):
    name = models.CharField(max_length = 50)
    description = models.TextField(blank = True, null = True)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"{self.name} - {self.description}"

class Expense(models.Model):
    ledger_entry = models.OneToOneField(
        LedgerEntry, on_delete=models.CASCADE, null=True, blank=True
    )
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    amount = models.FloatField(default=0)
    expense_type = models.ForeignKey(ExpenseAccount, on_delete = models.CASCADE)
    supplier = models.CharField(max_length = 100, blank = True, null = True)
    import_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    description = models.TextField(blank = True, null = True)
    actual_date = models.DateTimeField(default=timezone.now)
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateTimeField(blank=True, null=True)
    reversed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reversed_expenses",
    )
    reason_for_reversal = models.TextField(blank=True, null=True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    added_at = models.DateTimeField(auto_now_add = True)

    def __str__(self):
        return f"${self.amount:0.2f} for Account {self.account}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.actual_date:
            self.actual_date = timezone.now()
        if self.ledger_entry_id:
            self.account = self.ledger_entry.account
            self.amount = abs(Decimal(self.ledger_entry.amount))
        else:
            if not self.account_id:
                raise ValueError("An account is required to record an expense.")
            self.ledger_entry = LedgerEntry.objects.create(
                account=self.account,
                entry_type=LedgerEntry.DEBIT,
                amount=Decimal(str(self.amount)),
                running_balance=Decimal("0.00"),
                actual_date=self.actual_date,
                transaction_type="expense",
                reference=uuid.uuid4(),
            )
            self.amount = abs(Decimal(self.ledger_entry.amount))
            LedgerEntry.recalculate_account_balances(self.account_id)
            self.ledger_entry.refresh_from_db(fields=["running_balance"])
        super().save(*args, **kwargs)

class Receipt(models.Model):
    expense = models.OneToOneField(Expense, on_delete = models.SET_NULL, null = True)
    image = models.ImageField(upload_to = 'receipts/')
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"Receipt for Expense {self.expense}"

class GeneralExpense(models.Model):
    expense = models.OneToOneField(Expense, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"General Expense {self.expense}"

class CapitalExpense(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='capital_expenses')
    expense = models.OneToOneField(Expense, on_delete=models.SET_NULL, null = True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Capital Expense {self.expense if self.expense else 'N/A'}"

class FundsTransfer(models.Model):
    from_account_ledger_entry = models.OneToOneField(
        LedgerEntry,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transfer_out",
    )
    to_account_ledger_entry = models.OneToOneField(
        LedgerEntry,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transfer_in",
    )
    from_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="from_account"
    )
    to_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="to_account"
    )
    amount = models.FloatField(default=0)
    description = models.TextField(blank = True, null = True)
    initiated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="initiated_by"
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="transfer_accepted_by",
    )
    added_at = models.DateTimeField(auto_now_add = True)
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateField(blank=True, null=True)
    reversed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfer_reversed_by",
    )
    reason_for_reversal = models.TextField(blank=True, null=True)

    def __str__(self):
        return (
            f"Transfer of ${self.amount:0.2f} from {self.from_account} "
            f"to {self.to_account}"
        )

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.from_account_ledger_entry_id and not self.to_account_ledger_entry_id:
            if not self.from_account_id or not self.to_account_id:
                raise ValueError("Both accounts are required for a funds transfer.")
            if self.from_account_id == self.to_account_id:
                raise ValueError("A funds transfer must use two different accounts.")
            amount = Decimal(str(self.amount))
            if amount <= 0:
                raise ValueError("A funds transfer amount must be greater than zero.")

            list(
                Account.objects.select_for_update()
                .filter(pk__in=[self.from_account_id, self.to_account_id])
                .order_by("pk")
            )
            reference = uuid.uuid4()
            self.from_account_ledger_entry = LedgerEntry.objects.create(
                account=self.from_account,
                amount=amount,
                entry_type=LedgerEntry.DEBIT,
                running_balance=Decimal("0.00"),
                transaction_type="transfer out",
                reference=reference,
            )
            self.to_account_ledger_entry = LedgerEntry.objects.create(
                account=self.to_account,
                amount=amount,
                entry_type=LedgerEntry.CREDIT,
                running_balance=Decimal("0.00"),
                transaction_type="transfer in",
                reference=reference,
            )
            self.amount = abs(Decimal(self.from_account_ledger_entry.amount))
        elif not self.from_account_ledger_entry_id or not self.to_account_ledger_entry_id:
            raise ValueError("Both ledger entries are required for a linked transfer.")
        else:
            self.from_account = self.from_account_ledger_entry.account
            self.to_account = self.to_account_ledger_entry.account
            self.amount = abs(Decimal(self.from_account_ledger_entry.amount))

        if not self.description:
            self.description = (
                f"Transfer from {self.from_account} to {self.to_account}"
            )

        super().save(*args, **kwargs)
    
class Charge(models.Model): 
    ledger_entry = models.OneToOneField(
        LedgerEntry, on_delete=models.CASCADE, null=True, blank=True
    )
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    amount = models.FloatField(default=0)
    description = models.TextField(blank = True, null = True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    added_at = models.DateTimeField(auto_now_add = True)
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateTimeField(blank=True, null=True)
    reversed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charge_reversed_by",
    )
    reason_for_reversal = models.TextField(blank=True, null=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.ledger_entry_id:
            self.account = self.ledger_entry.account
            self.amount = abs(Decimal(self.ledger_entry.amount))
        else:
            if not self.account_id:
                raise ValueError("An account is required to record a charge.")
            self.ledger_entry = LedgerEntry.objects.create(
                account=self.account,
                amount=Decimal(str(self.amount)),
                entry_type=LedgerEntry.DEBIT,
                running_balance=Decimal("0.00"),
                transaction_type="charge",
                reference=uuid.uuid4(),
            )
            self.amount = abs(Decimal(self.ledger_entry.amount))

        if not self.description:
            self.description = f"Charge for {self.account}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Charge of ${self.amount:0.2f} for {self.account}"

class ExchangeRate(models.Model):
    base_currency = models.CharField(max_length=3, default = "USD")
    target_currency = models.CharField(max_length=3, default = "ZWL")
    rate = models.FloatField()
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Exchange rate from {self.base_currency} to {self.target_currency}: {self.rate}"
