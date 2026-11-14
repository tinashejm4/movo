from django.contrib import admin

from .models import Vehicle,VehicleAssignment, MileageRecord, FuelRecord, ServiceRecord, InsurancePolicy

# Register your models here.
admin.site.register(Vehicle)
admin.site.register(VehicleAssignment)
admin.site.register(MileageRecord)
admin.site.register(FuelRecord)
admin.site.register(ServiceRecord)
admin.site.register(InsurancePolicy)