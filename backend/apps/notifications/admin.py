from django.contrib import admin

from .models import DeviceToken, Notification, NotificationOutbox


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "app", "platform", "is_active", "last_seen_at")
    list_filter = ("app", "platform", "is_active")
    search_fields = ("user__username", "token")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "package", "created_at", "read_at")
    list_filter = ("event_type",)
    search_fields = ("user__username", "package__slug")


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(admin.ModelAdmin):
    list_display = ("notification", "status", "attempts", "delivered_at")
    list_filter = ("status",)
