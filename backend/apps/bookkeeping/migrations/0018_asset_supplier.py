from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0017_expense_import_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="supplier",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
