from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0011_ledger_entry_links"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ledgerentry",
            name="actual_date",
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
