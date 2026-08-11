from django.contrib import admin
from .models import SuburbSearchLog, Package, PackageStatus, Invoice,Price

# Register your models here.
admin.site.register(PackageStatus)
admin.site.register(Invoice)
admin.site.register(Price)


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
	list_display = ("id", "slug", "sender", "receiver", "city", "added_at")
	search_fields = ("slug", "sender__user__username", "receiver__user__username")
	readonly_fields = ("slug",)

@admin.register(SuburbSearchLog)
class SuburbSearchLogAdmin(admin.ModelAdmin):
	list_display = ("query", "normalized_query", "result_count", "had_results", "user", "created_at")
	list_filter = ("had_results", "created_at")
	search_fields = ("query", "normalized_query", "user__username")
	ordering = ("-created_at",)
