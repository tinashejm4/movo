from django.contrib import admin

from .models import (Staff, Driver, Shop, Customer, Contact, 
Identification, ProfileImage, ShopRegistration, DriverLicence, Vehicle)

admin.site.register(Staff)
admin.site.register(Driver)
admin.site.register(Shop)
admin.site.register(Customer)
admin.site.register(Contact)
admin.site.register(Identification)
admin.site.register(ProfileImage)
admin.site.register(ShopRegistration)
admin.site.register(DriverLicence)
admin.site.register(Vehicle)