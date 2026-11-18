import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0019_remove_capitalexpense_account_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="expense",
            name="actual_date",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
