from datetime import datetime, timedelta
import math
from django.utils import timezone

from django.contrib.auth.models import User
from django.db import models

class Branch(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    start_date = models.DateField(auto_now_add=True)
    
    def __str__(self):
        return f'{self.name}'
    
# ______________________________________________________________________________________

class Staff(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    position = models.CharField(max_length=50)
    date_joined = models.DateField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    date_joined = models.DateField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class Biker(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    date_joined = models.DateField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

# ______________________________________________________________________________________

class Contact(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=50)
    phone_number2 = models.CharField(max_length=50, null = True, blank = True)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class Address(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    address = models.CharField(max_length=150, null = True, blank = True)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class Identification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    id_number = models.CharField(max_length=50)
    id_image  = models.ImageField(default = 'identification_images/identification_image.png', upload_to='identification_images')

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class ProfileImage(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_image  = models.ImageField(default = 'profile_pics/profile_default.png', upload_to='profile_pics')

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'


class OTP(models.Model):
    username = models.CharField(max_length=150)
    otp_code = models.CharField(max_length=6)
    expiry_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        minutes_to_add = 25
        self.expiry_time = timezone.now() + timedelta(minutes=minutes_to_add)  # Set expiry time to 5 minutes from now
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.username} - {self.otp_code}'


class Suburb(models.Model):
    city = models.ForeignKey('City', on_delete=models.CASCADE, related_name='suburbs')
    name = models.CharField(max_length=100)
    x_pos = models.DecimalField(max_digits=10, decimal_places=3)
    y_pos = models.DecimalField(max_digits=10, decimal_places=3)
    x_coord = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    y_coord = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['city', 'name'], name='uniq_suburb_name_per_city')
        ]
        ordering = ['city_id', 'name']

    def __str__(self):
        return f'{self.name} ({self.city.name}) @ ({self.x_pos}, {self.y_pos})'

    def distance_to(self, other):
        
        if not isinstance(other, Suburb):
            raise TypeError('distance_to expects a Suburb instance')
        if self.city_id != other.city_id:
            raise ValueError('Cannot calculate distance between suburbs in different cities')

        x1 = float(self.x_pos)
        y1 = float(self.y_pos)
        x2 = float(other.x_pos)
        y2 = float(other.y_pos)
        return math.dist((x1, y1), (x2, y2))

class City(models.Model):
    name = models.CharField(max_length=100)
    province = models.CharField(max_length=100, default='Harare')
    country = models.CharField(max_length=100, default='Zimbabwe')

    def __str__(self):
        return f'{self.name}, {self.province}, {self.country}'

class DriverDailySession(models.Model):
    driver = models.ForeignKey('Biker', on_delete=models.CASCADE, related_name='daily_sessions')
    date = models.DateField()
    start_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    end_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('driver', 'date')

    def __str__(self):
        return f'{self.driver.user.username} - {self.date}'
