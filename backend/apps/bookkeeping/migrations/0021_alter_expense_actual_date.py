from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookkeeping", "0020_alter_ledgerentry_actual_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="expense",
            name="actual_date",
            field=models.DateTimeField(),
        ),
    ]
