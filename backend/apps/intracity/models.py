import secrets
import uuid

from django.db import models
from django.contrib.auth.models import User
from apps.users.models import Customer, City, Biker, Suburb
from apps.bookkeeping.models import ExchangeRate
from apps.transporters.handover_verifiers import new_salt_hex


class Package(models.Model):
    slug = models.SlugField(max_length=250, null=False, blank=False, editable=False)
    sender = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="local_sender"
    )
    receiver = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="local_receiver"
    )
    is_sender_initiated = models.BooleanField(default=True)
    city = models.ForeignKey(City, on_delete=models.DO_NOTHING)
    biker = models.ForeignKey(Biker, on_delete=models.SET_NULL, null=True, blank=True)
    pickup_area = models.ForeignKey(
        Suburb,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pickup_area",
    )
    pickup_address = models.CharField(max_length=255)
    dropoff_area = models.ForeignKey(
        Suburb,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dropoff_area",
    )
    dropoff_address = models.CharField(max_length=255)
    sender_code = models.CharField(max_length=20)
    is_fast_delivery = models.BooleanField(default=False)
    receiver_code = models.CharField(max_length=20)
    comments = models.TextField(max_length=500, null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    is_renewed = models.BooleanField(default=False)
    renewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.id} {self.sender} to {self.receiver}"

    def generate_unique_slug(self):
        while True:
            candidate = f"mov-{secrets.token_hex(6)}"
            if not Package.objects.filter(slug=candidate).exists():
                return candidate

    def save(self, *args, **kwargs):
        previous_biker_id = None
        if self.pk:
            previous_biker_id = type(self).objects.filter(pk=self.pk).values_list(
                "biker_id", flat=True
            ).first()
        if not self.slug:
            self.slug = self.generate_unique_slug()
        super().save(*args, **kwargs)
        biker_was_saved = kwargs.get("update_fields") is None or "biker" in kwargs["update_fields"]
        if biker_was_saved and self.biker_id and self.biker_id != previous_biker_id:
            PackageAssignment.objects.create(package=self, biker_id=self.biker_id)


class PackageAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="assignments")
    biker = models.ForeignKey(Biker, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)
    pickup_salt = models.CharField(max_length=32, default=new_salt_hex)
    dropoff_salt = models.CharField(max_length=32, default=new_salt_hex)

class PackageStatus(models.Model):
    status_choices = [
        ("Pending", "Pending"),
        ("Assigned", "Assigned"),
        ("In Transit", "In Transit"),
        ("Delivered", "Delivered"),
        ("Cancelled", "Cancelled"),
        ("Expired", "Expired"),
    ]

    package = models.ForeignKey(Package, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=status_choices, default="Pending")
    comments = models.TextField(max_length=500, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.status} - {self.package.slug}"

class PackageImage(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="package_images/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    upload_id = models.UUIDField(unique=True, null=True, blank=True)
    upload_sha256 = models.CharField(max_length=64, blank=True)
    stage = models.CharField(max_length=10, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    assignment = models.ForeignKey(PackageAssignment, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Image for Package {self.package.slug}"


class HandoverAttempt(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    package = models.ForeignKey(Package, on_delete=models.CASCADE)
    biker = models.ForeignKey(Biker, on_delete=models.CASCADE)
    assignment = models.ForeignKey(PackageAssignment, on_delete=models.CASCADE)
    image = models.ForeignKey(PackageImage, on_delete=models.PROTECT, null=True, blank=True)
    stage = models.CharField(max_length=10)
    cash_received = models.BooleanField(default=False)
    fingerprint = models.CharField(max_length=64)
    code_valid = models.BooleanField(default=False)
    outcome = models.CharField(max_length=12)
    conflict_reason = models.CharField(max_length=100, blank=True)
    response_status = models.PositiveSmallIntegerField()
    response_data = models.JSONField(default=dict)
    captured_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    resolution_reason = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

class Invoice(models.Model):
    payment_methods = [
        ("Ecocash", "Ecocash"),
        ("Cash", "Cash"),
        ("PaynowEcocash", "PaynowEcocash"),
    ]

    package = models.OneToOneField(Package, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    exchange_rate = models.ForeignKey(
        ExchangeRate, on_delete=models.SET_NULL, null=True, blank=True
    )
    is_pay_forward = models.BooleanField(default=False)
    payment_method = models.CharField(
        max_length=20, choices=payment_methods, default="Cash", null=True, blank=True
    )
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return (
            f'Payment for {self.package.slug} - {"Paid" if self.is_paid else "Unpaid"}'
        )

    def amount_in_zig(self):
        if self.exchange_rate:
            return float(self.amount) * float(self.exchange_rate.rate)
        return None


class RefundReview(models.Model):
    OUTCOMES = [("pending_review", "Pending review"), ("refunded", "Refunded"), ("rejected", "Rejected")]

    invoice = models.OneToOneField(Invoice, on_delete=models.PROTECT, related_name="refund_review")
    recipient = models.ForeignKey(Customer, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=OUTCOMES, default="pending_review")
    reference = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)


class Price(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    rate_per_km = models.DecimalField(max_digits=10, decimal_places=2)
    fast_delivery_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.5
    )
    is_locked = models.BooleanField(default=False) #system cannot override this price once locked

    def __str__(self):
        return f"Price for {self.city.name} - Base: {self.base_price}, Rate per KM: {self.rate_per_km}, Fast Delivery Multiplier: {self.fast_delivery_multiplier}"


class SuburbSearchLog(models.Model):
    query = models.CharField(max_length=150)
    normalized_query = models.CharField(max_length=150)
    result_count = models.PositiveIntegerField(default=0)
    had_results = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.query} ({self.result_count})"


class EcocashPayment(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20)
    client_correlator = models.CharField(
        max_length=100, blank=True, null=True
    )  # for the client correlator used in the Ecocash API request
    request_response = models.JSONField(
        blank=True, null=True
    )  # for the first response from the Ecocash API when initiating the payment request
    provider_response = models.JSONField(
        blank=True, null=True
    )  # for the response from the Ecocash API after processing the payment
    is_successful = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"EcoCash Payment for Invoice {self.invoice.id} - {'Successful' if self.is_successful else 'Failed'}"


class PaynowPayment(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20)
    reference = models.CharField(max_length=100, unique=True)
    poll_url = models.URLField(max_length=200, blank=True, null=True)
    is_successful = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice: {self.invoice.id} - {'Successful' if self.is_successful else 'Failed'}"
