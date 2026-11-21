import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("vehicles", "0005_fuelrecord_expense")]

    operations = [
        migrations.CreateModel(
            name="FuelPrice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fuel_type", models.CharField(choices=[("petrol", "Petrol"), ("diesel", "Diesel")], max_length=10)),
                ("currency", models.CharField(choices=[("USD", "USD"), ("ZWG", "ZWG")], max_length=3)),
                ("price_per_litre", models.DecimalField(decimal_places=4, max_digits=10)),
                ("effective_date", models.DateField()),
                ("source", models.URLField(default="https://www.zera.co.zw/")),
                ("fetched_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["effective_date", "fetched_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="fuelprice",
            index=models.Index(fields=["fuel_type", "currency", "-effective_date"], name="vehicles_fu_fuel_ty_81b647_idx"),
        ),
        migrations.AddField(
            model_name="fuelrecord",
            name="fuel_type",
            field=models.CharField(choices=[("petrol", "Petrol"), ("diesel", "Diesel")], default="petrol", max_length=10),
        ),
        migrations.AddField(
            model_name="fuelrecord",
            name="fuel_price",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="fuel_records", to="vehicles.fuelprice"),
        ),
    ]
