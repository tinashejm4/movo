from django.db import models
from packages.models import Package

class Sale(models.Model):

    amount = models.IntegerField(default = 0)
    date_added = models.DateField(auto_now_add = True)
    package = models.OneToOneField(Package, on_delete = models.CASCADE)
    
    def __str__(self):
        return f"${amount:00}"
