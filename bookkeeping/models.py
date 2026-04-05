from django.db import models
from packages.models import Package, Batch

class Sale(models.Model):

    amount = models.FloatField(default = 0)
    added_at = models.DateField(auto_now_add = True)
    package = models.OneToOneField(Package, on_delete = models.CASCADE)
    
    def __str__(self):
        return f"${self.amount:00} for Package {self.package}"

class TransportPayment(models.Model):

    amount = models.FloatField(default = 0)
    added_at = models.DateField(auto_now_add = True)
    batch = models.OneToOneField(Batch, on_delete = models.CASCADE)
    
    def __str__(self):
        return f"${self.amount:00} for Batch {self.batch}"

class DropOffPayment(models.Model):
    amount = models.FloatField(default = 0)
    added_at = models.DateField(auto_now_add = True)
    batch = models.OneToOneField(Batch, on_delete = models.CASCADE)

    def __str__(self):
        return f"${self.amount:00} for Batch {self.batch}"
        
class PickUpPayment(models.Model):
    amount = models.FloatField(default = 0)
    added_at = models.DateField(auto_now_add = True)
    package = models.OneToOneField(Package, on_delete = models.CASCADE)

    def __str__(self):
        return f"${self.amount:00} for Batch {self.batch}"

