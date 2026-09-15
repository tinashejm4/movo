from django.conf import settings
from django.db import models


class DeviceToken(models.Model):
    """An FCM registration token owned by one authenticated app session."""

    class App(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        BIKER = "biker", "Biker"

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_device_tokens",
    )
    token = models.TextField(unique=True)
    app = models.CharField(max_length=20, choices=App.choices)
    platform = models.CharField(max_length=20, choices=Platform.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["user", "app", "is_active"])]

    def __str__(self):
        return f"{self.app}/{self.platform} device for user {self.user_id}"


class Notification(models.Model):
    """Persistent in-app record; FCM is only one delivery channel."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    package = models.ForeignKey(
        "intracity.Package",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    event_type = models.CharField(max_length=64)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERING = "delivering", "Delivering"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    notification = models.OneToOneField(
        Notification,
        on_delete=models.CASCADE,
        related_name="outbox",
    )
    idempotency_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
