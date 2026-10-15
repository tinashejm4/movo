from decimal import Decimal
import uuid

from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
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
            return float(balance.running_balance)
        if at_datetime:
            legacy_balance = LedgerEntry.objects.filter(account=self).filter(actual_date__lte=at_datetime)
        else:
            legacy_balance = LedgerEntry.objects.filter(account=self)
        legacy_balance = legacy_balance.order_by("-actual_date", "-pk").first()
        return (
            float(legacy_balance.running_balance)
            if legacy_balance
            else 0.00
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
    actual_date = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    transaction_type = models.CharField(max_length=255, choices=TRANSACTION_TYPES)
    reference = models.UUIDField()

    def __str__(self):
        return f"{self.account} - {self.entry_type} - {self.amount}"

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
        amount = round(abs(float(str(self.amount))), 2)
        if self.entry_type == self.DEBIT:
            amount = -amount
        elif self.entry_type != self.CREDIT:
            raise ValueError(f"Unsupported ledger entry type: {self.entry_type}")
        self.amount = float(amount)

        if self._state.adding:
            account = Account.objects.select_for_update().get(pk=self.account_id)
            self.running_balance = account.get_balance() + float(self.amount)

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
            self.amount = float(self.ledger_entry.amount)
        else:
            if not self.account_id:
                raise ValueError("An account is required to record an intracity sale.")
            amount = round(abs(float(str(self.amount))), 2)
            if not amount and self.invoice_id:
                amount = round(abs(float(str(self.invoice.amount))), 2)
            self.ledger_entry = LedgerEntry.objects.create(
                account=self.account,
                entry_type=LedgerEntry.CREDIT,
                amount=amount,
                running_balance=float("0.00"),
                transaction_type="sale",
                reference=uuid.uuid4(),
            )
            self.amount = float(self.ledger_entry.amount)

        if not self.description and self.invoice_id:
            self.description = self.invoice.package.slug

        super().save(*args, **kwargs)

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
    description = models.TextField(blank = True, null = True)
    actual_date = models.DateTimeField(auto_now_add=True)
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
        if self.ledger_entry_id:
            self.account = self.ledger_entry.account
            self.amount = abs(float(self.ledger_entry.amount))
        else:
            if not self.account_id:
                raise ValueError("An account is required to record an expense.")
            self.ledger_entry = LedgerEntry.objects.create(
                account=self.account,
                entry_type=LedgerEntry.DEBIT,
                amount=float(str(self.amount)),
                running_balance=float("0.00"),
                transaction_type="expense",
                reference=uuid.uuid4(),
            )
            self.amount = abs(float(self.ledger_entry.amount))
        super().save(*args, **kwargs)

class Receipt(models.Model):
    expense = models.OneToOneField(Expense, on_delete = models.CASCADE)
    image = models.ImageField(upload_to = 'receipts/')
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"Receipt for Expense {self.expense}"

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
            amount = float(str(self.amount))
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
                running_balance=float("0.00"),
                transaction_type="transfer out",
                reference=reference,
            )
            self.to_account_ledger_entry = LedgerEntry.objects.create(
                account=self.to_account,
                amount=amount,
                entry_type=LedgerEntry.CREDIT,
                running_balance=float("0.00"),
                transaction_type="transfer in",
                reference=reference,
            )
            self.amount = abs(float(self.from_account_ledger_entry.amount))
        elif not self.from_account_ledger_entry_id or not self.to_account_ledger_entry_id:
            raise ValueError("Both ledger entries are required for a linked transfer.")
        else:
            self.from_account = self.from_account_ledger_entry.account
            self.to_account = self.to_account_ledger_entry.account
            self.amount = abs(float(self.from_account_ledger_entry.amount))

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
            self.amount = abs(float(self.ledger_entry.amount))
        else:
            if not self.account_id:
                raise ValueError("An account is required to record a charge.")
            self.ledger_entry = LedgerEntry.objects.create(
                account=self.account,
                amount=float(str(self.amount)),
                entry_type=LedgerEntry.DEBIT,
                running_balance=float("0.00"),
                transaction_type="charge",
                reference=uuid.uuid4(),
            )
            self.amount = abs(float(self.ledger_entry.amount))

        if not self.description:
            self.description = f"Charge for {self.account}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Charge of ${self.amount:0.2f} for {self.account}"

class EndOfDayBalance(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    expected_balance = models.FloatField(default = 0)
    actual_balance = models.FloatField(default = 0)
    accepted = models.BooleanField(default = False)
    accepted_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True, related_name = "accepted_by")  
    added_at = models.DateField(auto_now_add = True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True, related_name="added_by")

    def __str__(self):
        return f"{self.account} {self.added_at}"
    
class ExchangeRate(models.Model):
    rate = models.FloatField(default = 0)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"Exchange Rate of {self.rate} added at {self.added_at}"