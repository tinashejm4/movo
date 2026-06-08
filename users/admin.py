from django.contrib import admin

from .models import (Staff, Branch, Customer, Contact, 
Identification, ProfileImage)

admin.site.register(Staff)
admin.site.register(Branch)
admin.site.register(Customer)
admin.site.register(Contact)
admin.site.register(Identification)
admin.site.register(ProfileImage)
