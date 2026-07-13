from django.db import models
from apps.intercity.models import Package, Batch, Payment
from apps.users.models import Branch
from django.contrib.auth.models import User

class Account(models.Model):
    name = models.CharField(max_length = 50)
    branch = models.ForeignKey(Branch, on_delete = models.CASCADE, blank = True, null = True)
    owner = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    currency = models.CharField(max_length = 10, default = "USD")
    description = models.TextField(blank = True, null = True)
    number = models.CharField(max_length = 20, blank = True, null = True)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"{self.name} - {self.number}"

class IntracitySale(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    invoice = models.OneToOneField('intracity.Invoice', on_delete=models.CASCADE, null=True, blank=True)
    amount = models.FloatField(default = 0)
    added_at = models.DateField(auto_now_add = True)

class InterCitySale(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    intercity_invoice = models.OneToOneField('intercity.Payment', on_delete = models.CASCADE, null=True, blank=True)
    amount = models.FloatField(default = 0)
    added_at = models.DateField(auto_now_add = True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    
    def __str__(self):
        return f"${self.amount:00} for InterCity Invoice {self.intercity_invoice}"

# class Receipt(models.Model):
#     sale = models.OneToOneField(Sale, on_delete = models.CASCADE)
#     image = models.ImageField(upload_to = 'receipts/')
#     added_at = models.DateField(auto_now_add = True)

#     def __str__(self):
#         return f"Receipt for Sale {self.sale}"

class ExpenseType(models.Model):
    name = models.CharField(max_length = 50)
    description = models.TextField(blank = True, null = True)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"{self.name} - {self.description}"

class Expense(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    expense_type = models.ForeignKey(ExpenseType, on_delete = models.CASCADE)
    amount = models.FloatField(default = 0)
    comment = models.TextField(blank = True, null = True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"${self.amount:00} for Account {self.account}"
    
class ExpenseReceipt(models.Model):
    expense = models.ForeignKey(Expense, on_delete = models.CASCADE)
    image = models.ImageField(upload_to = 'transport_expense_receipts/')
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"Receipt for Transport Expense {self.transport_expense}"

# this model is for transport expenses which are linked to a specific batch of packages, unlike general expenses which are linked to a branch account
class TransportExpense(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    expense_type = models.ForeignKey(ExpenseType, on_delete = models.CASCADE)
    Batch = models.ForeignKey(Batch, on_delete = models.CASCADE)
    transport_category = models.CharField(max_length = 50, default = "fuel")
    amount = models.FloatField(default = 0)
    comment = models.TextField(blank = True, null = True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"${self.amount:00} for Account {self.account}"

class TransportExpenseReceipt(models.Model):
    transport_expense = models.ForeignKey(TransportExpense, on_delete = models.CASCADE)
    image = models.ImageField(upload_to = 'transport_expense_receipts/')
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"Receipt for Transport Expense {self.transport_expense}"

class FundsTransfer(models.Model):
    from_account = models.ForeignKey(Account, on_delete = models.CASCADE, related_name="from_account")
    to_account = models.ForeignKey(Account, on_delete = models.CASCADE, related_name="to_account")
    amount = models.FloatField(default = 0)
    comment = models.TextField(blank = True, null = True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"Transfer of ${self.amount:00} from {self.from_account} to {self.to_account}"

class Charge(models.Model):
    account = models.ForeignKey(Account, on_delete = models.CASCADE)
    amount = models.FloatField(default = 0)
    comment = models.TextField(blank = True, null = True)
    added_by = models.ForeignKey(User, on_delete = models.SET_NULL, null = True)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"Charge of ${self.amount:00} for {self.branch}"

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
    
