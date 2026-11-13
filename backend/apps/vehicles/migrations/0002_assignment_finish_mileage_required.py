from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vehicles", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehicleassignment",
            name="finish_mileage_required",
            field=models.BooleanField(default=False),
        ),
    ]
