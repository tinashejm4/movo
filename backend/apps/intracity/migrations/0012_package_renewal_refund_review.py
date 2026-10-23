from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("intracity", "0011_packageimage_stage_packageimage_upload_id_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="package", name="is_renewed", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="package", name="renewed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AlterField(model_name="packagestatus", name="status", field=models.CharField(choices=[("Pending", "Pending"), ("Assigned", "Assigned"), ("In Transit", "In Transit"), ("Delivered", "Delivered"), ("Cancelled", "Cancelled"), ("Expired", "Expired")], default="Pending", max_length=20)),
        migrations.CreateModel(
            name="RefundReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("payment_method", models.CharField(max_length=20)),
                ("status", models.CharField(choices=[("pending_review", "Pending review"), ("refunded", "Refunded"), ("rejected", "Rejected")], default="pending_review", max_length=20)),
                ("reference", models.CharField(blank=True, max_length=100)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("invoice", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="refund_review", to="intracity.invoice")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="users.customer")),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
