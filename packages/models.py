from django.db import models
from django.contrib.auth.models import User
import random
import string

def generate_otp_code(n_letters,n_numbers):
    letters = ''.join(random.choices(string.ascii_uppercase, k=n_letters))
    numbers = ''.join(random.choices(string.digits, k=n_numbers))
    return f"{letters}{numbers}"

class PackageSize(models.Model):
    size = models.CharField(max_length = 20)

    def __str__(self):
        return f'{self.size}'

class Price(models.Model):
    package_size = models.ForeignKey(PackageSize, on_delete = models.CASCADE)
    price = models.FloatField(default = 0)
    active = models.BooleanField(default = True)
    added_at   = models.DateField(auto_now_add = True)

    def __str__(self):
        return f'{self.price} on {self.added_at}'

class Package(models.Model):
    slug = models.SlugField(max_length=250, null = False, blank =False, editable=False)
    name = models.CharField(max_length = 20)
    batch = models.ForeignKey(Batch, on_delete = models.CASCADE, related_name = "sender")
    sender = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "sender")
    receiver = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "receiver")
    size = models.ForeignKey(PackageSize, on_delete = models.CASCADE)
    price = models.ForeignKey(Price, on_delete = models.CASCADE)
    logged_by = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "logged_by")
    collected = models.BooleanField(default = False)
    collected_at = models.DateField(blank = True)
    added_at   = models.DateField(auto_now_add = True)

    def __str__(self):
        return f'{self.name}'

class City(models.Model):
    city = models.CharField(max_length=150)

    def __str__(self):
        return f'{self.city}'

class CitySection(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    section = models.CharField(max_length=150)

    def __str__(self):
        return f'{self.section}'

class Location(models.Model):
    section = models.ForeignKey(CitySection, on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    distance_from_cbd = models.FloatField(default = 0)

    def __str__(self):
        return f'{self.name}'

class Batch(models.Model):
    origin_location = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "from_shop")
    destination_location = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "to_shop")
    is_available = models.BooleanField(default = True)

    def __str__(self):
        return f'{self.origin_location} to {self.destination_location} - {self.id}'
  
class Trip(models.Model):
    driver = models.ForeignKey(User, on_delete = models.CASCADE, null = True)
    batch  = models.ForeignKey(Batch, on_delete = models.CASCADE)
    rate   = models.ForeignKey(Rate, on_delete = models.CASCADE)
    cost = models.FloatField(default = 0)
    added_at = models.DateField(auto_now_add = True)
    ended = models.BooleanField(default = False)
    ended_at = models.DateField(blank = True)

    def __str__(self):
        return batch

class Rate(models.Model):
    transport_rate = models.FloatField(default = 0, editable = False)
    dropoff_rate = models.FloatField(default = 0, editable = False)
    pickup_rate = models.FloatField(default = 0, editable = False)
    added_at = models.DateField(auto_now_add = True)

    def __str__(self):
        return f"${self.rate:00}"

# class SenderCode(models.Model):
#     package = models.OneToOneField(Package, on_delete = models.CASCADE)
#     code = models.CharField(max_length = 20)

#     def __str__(self):
#         return f'{self.package}'

    def save(self, *args, **kwargs):
        if not self.code:
            new_code = generate_code(2,4)
            while DriverCode.objects.filter(code=new_code).exists():
                new_code = generate_otp_code()
            self.code = new_code
        super().save(*args, **kwargs)

class ReceipientCode(models.Model):
    package = models.OneToOneField(Package, on_delete = models.CASCADE)
    code = models.CharField(max_length = 20)

    def __str__(self):
        return f'{self.package}'

    def save(self, *args, **kwargs):
        if not self.code:
            new_code = "P"+generate_otp_code(3,4)
            while DriverCode.objects.filter(code=new_code).exists():
                new_code = "P"+generate_otp_code(3,4)
            self.code = new_code
        super().save(*args, **kwargs)

class DriverCode(models.Model):
    batch = models.OneToOneField(Batch, on_delete = models.CASCADE)
    code = models.CharField(max_length = 20)

    def __str__(self):
        return f'{self.package}'

    def save(self, *args, **kwargs):
        if not self.code:
            new_code = "B"+generate_otp_code(2,4)
            while DriverCode.objects.filter(code=new_code).exists():
                new_code = "B"+generate_otp_code(2,4)
            self.code = new_code
        super().save(*args, **kwargs)