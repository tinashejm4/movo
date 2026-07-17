from django.contrib import admin

from .models import (OTP, Staff, Branch, Customer, Contact, 
Identification, ProfileImage, City, Suburb)

admin.site.register(Staff)
admin.site.register(Branch)
admin.site.register(Customer)
admin.site.register(Contact)
admin.site.register(City)
admin.site.register(Identification)
admin.site.register(ProfileImage)
admin.site.register(OTP)
admin.site.register(Suburb)
