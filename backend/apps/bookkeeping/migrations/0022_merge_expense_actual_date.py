import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0020_expense_actual_date_default"),
        ("bookkeeping", "0021_alter_expense_actual_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="expense",
            name="actual_date",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
