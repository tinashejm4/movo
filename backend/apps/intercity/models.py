from django.db import models
from django.contrib.auth.models import User
import random
import string
from apps.users.models import Branch, Customer, Staff
       
class PrePackage(models.Model):
    slug = models.SlugField(max_length=250, null = False, blank =False, editable=False)
    creation_code = models.CharField(max_length = 20)
    sender = models.ForeignKey(Customer, on_delete = models.CASCADE, related_name = "sender")
    receiver = models.ForeignKey(Customer, on_delete = models.CASCADE, related_name = "receiver")
    self_created = models.BooleanField(default = False)
    to_shop = models.ForeignKey(Branch, on_delete = models.CASCADE,default=None, related_name = "to_shop")
    added_at   = models.DateTimeField(auto_now_add = True)
    
    def __str__(self):
        return f'{self.creation_code} - {self.sender} to {self.receiver}'

class Batch(models.Model):
    sent_from_shop = models.ForeignKey(Branch, on_delete = models.CASCADE, related_name = "batch_sent_from_shop")
    sent_to_shop = models.ForeignKey(Branch, on_delete = models.CASCADE, related_name = "batch_sent_to_shop")
    is_available = models.BooleanField(default = True)
    added_at   = models.DateTimeField(auto_now_add = True)

    def __str__(self):
        return f'{self.id} - {self.sent_from_shop} to {self.sent_to_shop}'

class PackageDimension(models.Model):
    length = models.FloatField(default = 0)
    width = models.FloatField(default = 0)
    height = models.FloatField(default = 0)
    weight = models.FloatField(default = 0)
    dimensional_factor = models.IntegerField(default = 5000)

    def get_size(self):
        if self.get_charged_weight() <= 1:
            return "Small"
        elif self.get_charged_weight() <= 5:
            return "Medium" 
        elif self.get_charged_weight() <= 10:
            return "Large"
        else:
            return "Extra Large"
    
    def get_charged_weight(self):
        volumetric_weight = (self.length * self.width * self.height) / self.dimensional_factor
        return max(self.weight, volumetric_weight)

    def __str__(self):
        return f'{self.length}x{self.width}x{self.height} - {self.weight}kg'

class Price(models.Model):
    dimensional_factor = models.IntegerField(default = 5000)
    base_fee = models.FloatField(default = 2)
    insurance_fee = models.FloatField(default = 1)
    rate_per_kg = models.FloatField(default = 0.5)
    added_at   = models.DateTimeField(auto_now_add = True)

    def __str__(self):
        return f'Rate {self.rate_per_kg} - ${self.base_fee:00}'


class ExchangeRate(models.Model):
    """Exchange rate from USD to ZWL (ZWL per 1 USD)."""
    rate_to_zwl = models.FloatField(default=25.0)
    source = models.CharField(max_length=100, default='manual')
    updated_at = models.DateTimeField(auto_now=True)

    def convert_usd_to_zwl(self, usd_amount: float) -> float:
        return usd_amount * self.rate_to_zwl

    def __str__(self):
        return f'1 USD = {self.rate_to_zwl} ZWL ({self.source})'

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('ecocash', 'EcoCash'),
    ]
    
    CURRENCY_CHOICES = [
        ('usd', 'USD'),
        ('zwl', 'ZWL'),
    ]
    price = models.ForeignKey(Price, on_delete = models.CASCADE)
    amount = models.FloatField(default = 0) # self.price.base_fee + (self.price.rate_per_kg * charged_weight)
    is_pay_forward = models.BooleanField(default = False)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='usd')
    paid_at = models.DateTimeField(auto_now_add = True)

    def __str__(self):
        method_display = self.get_payment_method_display()
        currency_display = self.get_currency_display()
        if self.is_pay_forward:
            return f'Pay forward of {self.amount} {currency_display} via {method_display}'
        else:
            return f'Payment of {self.amount} {currency_display} via {method_display}'
    
class Package(models.Model):
    slug = models.SlugField(max_length=250, null = False, blank =False, editable=False)
    pre_package = models.OneToOneField(PrePackage, on_delete = models.CASCADE, default = None,null = True,)
    batch = models.ForeignKey(Batch, on_delete = models.CASCADE, related_name = "sender")
    dimensions = models.ForeignKey(PackageDimension, on_delete = models.CASCADE)
    payment = models.ForeignKey(Payment, on_delete = models.CASCADE)
    receiver_code = models.CharField(max_length = 20)
    description = models.CharField(max_length = 200, null = True, blank = True)
    logged_by = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "logged_by")
    is_collected = models.BooleanField(default = False)
    collected_at = models.DateTimeField(blank = True, null=True)
    added_at   = models.DateTimeField(auto_now_add = True, null=True)


    def __str__(self):
        return f'{self.batch.sent_from_shop} to {self.batch.sent_to_shop} - {self.description}'

class PaymentRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    external_id = models.CharField(max_length=64, unique=True)
    method = models.CharField(max_length=20)
    phone_number = models.CharField(max_length=50, null=True, blank=True)
    amount = models.FloatField(default=0)
    currency = models.CharField(max_length=10, default='usd')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.external_id} - {self.method} - {self.status}'

