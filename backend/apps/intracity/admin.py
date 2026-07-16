from django.contrib import admin
from .models import SuburbSearchLog

# Register your models here.


@admin.register(SuburbSearchLog)
class SuburbSearchLogAdmin(admin.ModelAdmin):
	list_display = ("query", "normalized_query", "result_count", "had_results", "user", "created_at")
	list_filter = ("had_results", "created_at")
	search_fields = ("query", "normalized_query", "user__username")
	ordering = ("-created_at",)
