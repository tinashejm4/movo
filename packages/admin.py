from django.contrib import admin

from .models import Package, Batch, Payment, PrePackage,PackageDimension, Price


admin.site.register(Package)
admin.site.register(Batch)  
admin.site.register(PrePackage)
admin.site.register(PackageDimension)
admin.site.register(Price)
admin.site.register(Payment)
