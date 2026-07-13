import secrets

from django.db import models
from apps.users.models import Customer, City,Biker, Suburb
from apps.bookkeeping.models import ExchangeRate

class Package(models.Model):
    slug = models.SlugField(max_length=250, null = False, blank =False, editable=False)
    sender = models.ForeignKey(Customer, on_delete = models.CASCADE, related_name = "local_sender")
    receiver = models.ForeignKey(Customer, on_delete = models.CASCADE, related_name = "local_receiver")
    is_sender_initiated = models.BooleanField(default = True)
    city  = models.ForeignKey(City, on_delete=models.DO_NOTHING)
    biker = models.ForeignKey(Biker, on_delete = models.SET_NULL, null = True, blank = True)
    pickup_area = models.ForeignKey(Suburb, on_delete=models.SET_NULL, null = True, blank = True, related_name='pickup_area')
    pickup_address = models.CharField(max_length=255)
    dropoff_area = models.ForeignKey(Suburb, on_delete=models.SET_NULL, null = True, blank = True, related_name='dropoff_area')
    dropoff_address = models.CharField(max_length=255)
    sender_code = models.CharField(max_length = 20)
    is_fast_delivery = models.BooleanField(default = False)
    receiver_code = models.CharField(max_length = 20)
    comments = models.TextField(max_length=500, null = True, blank = True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    added_at   = models.DateTimeField(auto_now_add = True)
    
    def __str__(self):
        return f'{self.sender} to {self.receiver}'
    
    def generate_unique_slug(self):
        while True:
            candidate = f"pkg-{secrets.token_hex(6)}"
            if not Package.objects.filter(slug=candidate).exists():
                return candidate

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.generate_unique_slug()
        super().save(*args, **kwargs)
    
class PackageStatus(models.Model):
    status_choices = [
        ('Pending', 'Pending'),
        ('In Transit', 'In Transit'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
    ]

    package = models.ForeignKey(Package, on_delete = models.CASCADE)
    status = models.CharField(max_length=20, choices=status_choices, default='Pending')
    updated_at = models.DateTimeField(auto_now_add = True)
    
    def __str__(self):
        return f'{self.package.creation_code} - {self.status}'

class Invoice(models.Model):
    package = models.OneToOneField(Package, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    exchange_rate = models.ForeignKey(ExchangeRate, on_delete=models.SET_NULL, null=True, blank=True)
    is_pay_forward = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f'Payment for {self.package.slug} - {"Paid" if self.is_paid else "Unpaid"}'

    def amount_in_zig(self):
        if self.exchange_rate:
            return self.amount * self.exchange_rate.rate
        return None

class Price(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    rate_per_km = models.DecimalField(max_digits=10, decimal_places=2)
    fast_delivery_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=1.5)
    
    def __str__(self):
        return f'Price for {self.city.name} - Base: {self.base_price}, Rate per KM: {self.rate_per_km}, Fast Delivery Multiplier: {self.fast_delivery_multiplier}'
