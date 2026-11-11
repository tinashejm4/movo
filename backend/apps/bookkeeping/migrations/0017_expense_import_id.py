from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0016_asset_exchangerate_base_currency_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="import_id",
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
    ]
