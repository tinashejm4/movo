from datetime import timedelta
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
        return f'{self.user.first_name} {self.user.last_name} - {self.position}'

class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    date_joined = models.DateField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class Biker(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    date_joined = models.DateField(auto_now_add=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

# ______________________________________________________________________________________

class Contact(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=50)
    phone_number2 = models.CharField(max_length=50, null = True, blank = True)
    address = models.CharField(max_length=150, null = True, blank = True)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class Identification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    id_number = models.CharField(max_length=50)
    id_image  = models.ImageField(default = 'identification_images/identification_image.png', upload_to='identification_images')

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class NextOfKin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=50)
    relationship = models.CharField(max_length=50)

    def __str__(self):
        return f'{self.name} ({self.relationship}) - {self.user.first_name} {self.user.last_name}'

class Licence(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    licence_number = models.CharField(max_length=50)
    licence_image  = models.ImageField(default = 'licence_images/licence_image.png', upload_to='licence_images')

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

class ProfileImage(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_image  = models.ImageField(default = 'profile_pics/profile_default.png', upload_to='profile_pics')

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

# ______________________________________________________________________________________

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

# ______________________________________________________________________________________

class Suburb(models.Model):
    DISTANCE_CORRECTION_REFERENCE_KM = 10.0
    DISTANCE_CORRECTION_REFERENCE_FACTOR = 1.3

    city = models.ForeignKey('City', on_delete=models.CASCADE, related_name='suburbs')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=False)
    x_coord = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    y_coord = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['city', 'name'], name='uniq_suburb_name_per_city')
        ]
        ordering = ['city_id', 'name']

    def __str__(self):
        return f'{self.name} ({self.city.name}) @ ({self.x_coord}, {self.y_coord}) is {"active" if self.is_active else "inactive"}'

    def distance_to(self, other):
        if not isinstance(other, Suburb):
            raise TypeError('distance_to expects a Suburb instance')
        if self.city_id != other.city_id:
            raise ValueError('Cannot calculate distance between suburbs in different cities')

        x1 = float(self.x_coord)
        y1 = float(self.y_coord)
        x2 = float(other.x_coord)
        y2 = float(other.y_coord)
        coordinate_distance_km = math.dist((x1, y1), (x2, y2)) * 111  # Approximate conversion from degrees to kilometers
        correction_slope = (
            self.DISTANCE_CORRECTION_REFERENCE_FACTOR - 1
        ) / self.DISTANCE_CORRECTION_REFERENCE_KM
        correction_factor = 1 + (correction_slope * coordinate_distance_km)
        distance_km = coordinate_distance_km * correction_factor

        return distance_km

class SuburbAlias(models.Model):
    suburb = models.ForeignKey('Suburb', on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['suburb', 'alias'], name='uniq_suburb_alias_per_suburb')
        ]

    def __str__(self):
        return f'{self.alias} ({self.suburb.name})'

class City(models.Model):
    name = models.CharField(max_length=100)
    province = models.CharField(max_length=100, default='Harare')
    country = models.CharField(max_length=100, default='Zimbabwe')

    def __str__(self):
        return f'{self.name}, {self.province}, {self.country}'

# ______________________________________________________________________________________