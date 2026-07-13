# Generated manually to add intracity billing models

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intracity", "0001_initial"),
        ("users", "__first__"),
    ]

    operations = [
        migrations.CreateModel(
            name="Price",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("base_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("rate_per_km", models.DecimalField(decimal_places=2, max_digits=10)),
                ("fast_delivery_multiplier", models.DecimalField(decimal_places=2, default=1.5, max_digits=5)),
                ("city", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="users.city")),
            ],
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "payment_method",
                    models.CharField(
                        choices=[("cash", "Cash"), ("ecocash", "EcoCash")],
                        default="cash",
                        max_length=20,
                    ),
                ),
                ("is_pay_forward", models.BooleanField(default=False)),
                ("is_paid", models.BooleanField(default=False)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                (
                    "package",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to="intracity.package"),
                ),
            ],
        ),
    ]
