from decimal import Decimal
from django.utils import timezone
from django.db import models
from apps.intercity.models import Package, Batch, Payment
from apps.users.models import Branch
from django.contrib.auth.models import User


def get_previous_balance(account):
    previous_balance = AccountBalance.objects.filter(account=account).order_by('-pk').first()
    if previous_balance:
        previous_balance = previous_balance.running_balance
    else:
        previous_balance = float("0.00")
    return previous_balance

def update_balances(account, running_balance, amount, operation):
    future_balances = AccountBalance.objects.filter(account=account, id__gt=running_balance.id).order_by('id')
    for balance in future_balances:
        if operation == "+":
            balance.running_balance += amount
        elif operation == "-":
            balance.running_balance -= amount
        AccountBalance.objects.bulk_update(future_balances, ['running_balance'])

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

    def get_balance(self, at_date=None):
        if at_date:
            balance = AccountBalance.objects.filter(account=self, updated_at__lte=at_date).order_by('-pk').first()
        else:
            balance = AccountBalance.objects.filter(account=self).order_by('-pk').first()
        return balance.running_balance if balance else float("0.00")

class AccountBalance(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    running_balance = models.FloatField(default = 0)
    is_cancelled = models.BooleanField(default = False)
    updated_at = models.DateField(auto_now = True)
    # Ensure that the primary key is used for ordering instead of the updated_at field

    def __str__(self):
        return f"Balance for Account {self.account}: ${self.running_balance:0.2f}"

class IntracitySale(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    invoice = models.OneToOneField('intracity.Invoice', on_delete=models.CASCADE, null=True, blank=True)
    description = models.TextField(blank = True, null = True)
    running_balance = models.ForeignKey(AccountBalance, on_delete = models.CASCADE, null = True, blank = True)
    amount = models.FloatField(default = 0)
    added_at = models.DateTimeField(auto_now_add = True)

    def __str__(self):
        return f"{self.account} -{self.invoice}- {self.amount}"

    def save(self, *args, **kwargs):
        if not self.description:
            self.description = f"{self.invoice.package.slug}"
        if not self.running_balance:
            self.running_balance = AccountBalance.objects.create(
                account=self.account,
                running_balance=get_previous_balance(self.account) + self.amount
            )
        super().save(*args, **kwargs)

class ExpenseAccount(models.Model):
    name = models.CharField(max_length = 50)
    description = models.TextField(blank = True, null = True)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"{self.name} - {self.description}"

class Expense(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    expense_type = models.ForeignKey(ExpenseAccount, on_delete = models.CASCADE)
    amount = models.FloatField(default = 0)
    supplier = models.CharField(max_length = 100, blank = True, null = True)
    description = models.TextField(blank = True, null = True)
    running_balance = models.OneToOneField(AccountBalance, on_delete = models.CASCADE, null = True, blank = True)
    is_reversed = models.BooleanField(default = False)
    reversed_at = models.DateField(blank = True, null = True)
    reversed_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True, related_name="reversed_expenses")
    reason_for_reversal = models.TextField(blank = True, null = True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    added_at = models.DateTimeField(auto_now_add = True)

    def __str__(self):
        return f"${self.amount:00} for Account {self.account}"

    def save(self, *args, **kwargs):
        if not self.running_balance:
            self.running_balance = AccountBalance.objects.create(
                account=self.account,
                running_balance=get_previous_balance(self.account) - float(self.amount) 
            )
        super().save(*args, **kwargs)

    def reverse(self, user, reason):
        self.is_reversed = True
        self.reversed_at = timezone.now().date()
        self.reversed_by = user
        self.reason_for_reversal = reason
        self.save()
        self.running_balance.is_cancelled = True
        self.running_balance.save()
        update_balances(self.account, self.running_balance, float(self.amount), "+")

class Receipt(models.Model):
    expense = models.OneToOneField(Expense, on_delete = models.CASCADE)
    image = models.ImageField(upload_to = 'receipts/')
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"Receipt for Expense {self.expense}"

class FundsTransfer(models.Model):
    from_account = models.ForeignKey(Account, on_delete = models.CASCADE, related_name="from_account")
    to_account = models.ForeignKey(Account, on_delete = models.CASCADE, related_name="to_account")
    amount = models.FloatField(default = 0)
    description = models.TextField(blank = True, null = True)
    from_account_running_balance = models.OneToOneField(AccountBalance, on_delete = models.CASCADE, null = True, blank = True, related_name="from_account_running_balance")
    to_account_running_balance = models.OneToOneField(AccountBalance, on_delete = models.CASCADE, null = True, blank = True, related_name="to_account_running_balance")
    initiated_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True, related_name="initiated_by")
    approved_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True, related_name="transfer_accepted_by")
    added_at = models.DateTimeField(auto_now_add = True)
    is_reversed = models.BooleanField(default = False)
    reversed_at = models.DateField(blank = True, null = True)
    reversed_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True, blank = True, related_name="transfer_reversed_by")
    reason_for_reversal = models.TextField(blank = True, null = True)

    def __str__(self):
        return f"Transfer of ${self.amount:00} from {self.from_account} to {self.to_account}"

    def save(self, *args, **kwargs):
        if not self.description:
            self.description = f"Transfer from {self.from_account} to {self.to_account}"
        if not self.from_account_running_balance:
            self.from_account_running_balance = AccountBalance.objects.create(
                account=self.from_account,
                running_balance=get_previous_balance(self.from_account) - float(self.amount)
            )
        if not self.to_account_running_balance:
            self.to_account_running_balance = AccountBalance.objects.create(
                account=self.to_account,
                running_balance=get_previous_balance(self.to_account) + float(self.amount)
            )
        super().save(*args, **kwargs)

    def reverse(self, user, reason):
        self.is_reversed = True
        self.reversed_at = timezone.now().date()
        self.reversed_by = user
        self.reason_for_reversal = reason
        self.save()
        self.from_account_running_balance.is_cancelled = True
        self.from_account_running_balance.save()
        self.to_account_running_balance.is_cancelled = True
        self.to_account_running_balance.save()
        update_balances(self.from_account, self.from_account_running_balance, float(self.amount), "+")
        update_balances(self.to_account, self.to_account_running_balance, float(self.amount), "-")

class Charge(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    amount = models.FloatField(default = 0)
    running_balance = models.OneToOneField(AccountBalance, on_delete = models.CASCADE, null = True, blank = True)
    description = models.TextField(blank = True, null = True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    added_at = models.DateTimeField(auto_now_add = True)
    is_reversed = models.BooleanField(default = False)
    reversed_at = models.DateField(blank = True, null = True)
    reversed_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True, blank = True, related_name="charge_reversed_by")
    reason_for_reversal = models.TextField(blank = True, null = True)

    def save(self, *args, **kwargs):
        if not self.description:
            self.description = f"Charge for {self.account}"
        if not self.running_balance:
            self.running_balance = AccountBalance.objects.create(
                account=self.account,
                running_balance=get_previous_balance(self.account) - float(self.amount)
            )
        super().save(*args, **kwargs)

    def reverse(self, user, reason):
        self.is_reversed = True
        self.reversed_at = timezone.now().date()
        self.reversed_by = user
        self.reason_for_reversal = reason
        self.save()
        self.running_balance.is_cancelled = True
        self.running_balance.save()
        update_balances(self.account, self.running_balance, float(self.amount), "+")

    def __str__(self):
        return f"Charge of ${self.amount:00} for {self.account}"

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
