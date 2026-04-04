from django.contrib.auth.models import User
from django.db import models
from packages.models import Location

class Staff(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    position = models.CharField(max_length=50)
    date_joined = models.DateField(auto_now_add=True)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

class Driver(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    date_joined = models.DateField(auto_now_add=True)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

class Shop(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    shop_name = models.CharField(max_length=100)

    location = models.ForeignKey(Location, on_delete = models.CASCADE)

    date_joined = models.DateField(auto_now_add=True)

    
    def __str__(self):
        return f'{self.first_name} {self.last_name} - {self.location}'

class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    date_joined = models.DateField(auto_now_add=True)

# ______________________________________________________________________________________

class Contact(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=50)
    phone_number2 = models.CharField(max_length=50, null = True, blank = True)
    address = models.CharField(max_length=150, null = True, blank = True)

class Identification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    id_number = models.CharField(max_length=50)
    id_image  = models.ImageField(default = 'identification_images/identification_image.png', upload_to='identification_images')

class ProfileImage(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_image  = models.ImageField(default = 'profile_pics/profile_default.png', upload_to='profile_pics')

class ShopRegistration(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    registration_number = models.CharField(max_length=50)
    registration_date = models.CharField(max_length=50)
# ______________________________________________________________________________________

class DriverLicence(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    licence_id = models.CharField(max_length = 50)
    licence_image  = models.ImageField(default = 'driver_licence/driver_licence.png', upload_to='driver_licence')

    def __str__(self):
        return f'{self.first_name} {self.last_name} - {self.location}'

class Vehicle(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    license_number = models.CharField(max_length=50)
    vehicle_type = models.CharField(max_length=50)
    vehicle_color = models.CharField(max_length=50)

    def __str__(self):
        return f'{self.vehicle_type}'

