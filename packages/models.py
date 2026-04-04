from django.db import models
from django.contrib.auth.models import User

class PackageSize(models.Model):
    size = models.CharField(max_length = 20)

    def __str__(self):
        return f'{self.size}'

class Price(models.Model):
    package_size = models.ForeignKey(PackageSize, on_delete = models.CASCADE)
    price = models.FloatField(default = 0)
    active = models.BooleanField(default = True)
    date_added   = models.DateField(auto_now_add = True)

    def __str__(self):
        return f'{self.price} on {self.date_added}'

class Package(models.Model):
    slug = models.SlugField(max_length=250, null = False, blank =False, editable=False)
    name = models.CharField(max_length = 20)
    sender = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "sender")
    receiver = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "receiver")
    from_shop = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "from_shop")
    to_shop = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "to_shop")
    size = models.ForeignKey(PackageSize, on_delete = models.CASCADE)
    price = models.ForeignKey(Price, on_delete = models.CASCADE)
    logged_by = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "logged_by")
    date_added   = models.DateField(auto_now_add = True)


    def __str__(self):
        return f'{self.name}'

class ReceiverCode(models.Model):
    package = models.OneToOneField(Package, on_delete = models.CASCADE)
    code = models.CharField(max_length = 20)

    def __str__(self):
        return f'{self.package}'

class PackageStatus(models.Model):
    package = models.ForeignKey(Package, on_delete = models.CASCADE)
    status = models.IntegerField(default = 0)
    date_added = models.DateField(auto_now_add = True)

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

    def __str__(self):
        return f'{self.name}'
