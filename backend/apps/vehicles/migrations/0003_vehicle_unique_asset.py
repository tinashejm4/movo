from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vehicles", "0002_vehicle_asset"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="vehicle",
            constraint=models.UniqueConstraint(fields=("asset",), name="vehicles_unique_asset"),
        ),
    ]
