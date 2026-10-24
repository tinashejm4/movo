from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("intracity", "0013_optional_dropoff_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="handoverattempt",
            name="image",
            field=models.ForeignKey(
                to="intracity.packageimage",
                on_delete=django.db.models.deletion.PROTECT,
                null=True,
                blank=True,
            ),
        ),
    ]
