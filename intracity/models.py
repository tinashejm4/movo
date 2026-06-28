from django.db import models

class PrePackage(models.Model):
    package_id = models.CharField(max_length=20, unique=True)
