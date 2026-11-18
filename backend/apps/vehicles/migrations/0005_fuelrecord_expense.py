import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0020_expense_actual_date_default"),
        ("vehicles", "0004_vehicle_asset_vehicle_vehicles_unique_asset"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="fuelrecord",
            name="currency",
        ),
        migrations.RemoveField(
            model_name="fuelrecord",
            name="receipt_reference",
        ),
        migrations.RemoveField(
            model_name="fuelrecord",
            name="station",
        ),
        migrations.RemoveField(
            model_name="fuelrecord",
            name="total_cost",
        ),
        migrations.AddField(
            model_name="fuelrecord",
            name="expense",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="fuel_record",
                to="bookkeeping.expense",
            ),
        ),
    ]
