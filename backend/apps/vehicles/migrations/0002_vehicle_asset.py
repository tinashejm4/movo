import django.db.models.deletion
from django.db import migrations, models


def create_vehicle_assets(apps, schema_editor):
    Vehicle = apps.get_model("vehicles", "Vehicle")
    Asset = apps.get_model("bookkeeping", "Asset")
    database = schema_editor.connection.alias
    for vehicle in Vehicle.objects.using(database).iterator():
        asset = Asset.objects.using(database).create(
            asset_type="vehicle",
            name=f"{vehicle.make} {vehicle.model}"[:100],
            unique_identifier=vehicle.registration_number,
        )
        Vehicle.objects.using(database).filter(pk=vehicle.pk).update(asset_id=asset.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0016_asset_exchangerate_base_currency_and_more"),
        ("vehicles", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehicle",
            name="asset",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fleet_vehicles",
                to="bookkeeping.asset",
            ),
        ),
        migrations.RunPython(create_vehicle_assets),
        migrations.AlterField(
            model_name="vehicle",
            name="asset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fleet_vehicles",
                to="bookkeeping.asset",
            ),
        ),
    ]
