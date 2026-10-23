import uuid
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_intracity_sale_ledger_entries(apps, schema_editor):
    Sale = apps.get_model("bookkeeping", "IntracitySale")
    LedgerEntry = apps.get_model("bookkeeping", "LedgerEntry")
    AccountBalance = apps.get_model("bookkeeping", "AccountBalance")
    Expense = apps.get_model("bookkeeping", "Expense")
    Charge = apps.get_model("bookkeeping", "Charge")
    database = schema_editor.connection.alias
    running_balances = {}

    for model in (Sale, Expense, Charge):
        model.objects.using(database).filter(actual_date__isnull=True).update(
            actual_date=models.F("added_at")
        )

    sales = Sale.objects.using(database).order_by("account_id", "pk")
    for sale in sales.iterator():
        amount = abs(Decimal(str(sale.amount)))
        if sale.running_balance_id:
            balance = AccountBalance.objects.using(database).filter(
                pk=sale.running_balance_id
            ).values_list("running_balance", flat=True).first()
            running_balance = Decimal(str(balance))
        else:
            running_balance = running_balances.get(
                sale.account_id, Decimal("0.00")
            ) + amount

        entry = LedgerEntry.objects.using(database).create(
            account_id=sale.account_id,
            entry_type="credit",
            amount=amount,
            running_balance=running_balance,
            transaction_type="sale",
            reference=uuid.uuid4(),
        )
        Sale.objects.using(database).filter(pk=sale.pk).update(
            ledger_entry_id=entry.pk
        )
        running_balances[sale.account_id] = running_balance


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0009_alter_charge_added_at_alter_expense_added_at_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LedgerEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "entry_type",
                    models.CharField(
                        choices=[("credit", "Credit"), ("debit", "Debit")],
                        max_length=10,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "running_balance",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "transaction_type",
                    models.CharField(
                        choices=[
                            ("sale", "Sale"),
                            ("expense", "Expense"),
                            ("transfer", "Transfer"),
                            ("charge", "Charge"),
                        ],
                        max_length=255,
                    ),
                ),
                ("reference", models.UUIDField()),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ledger_entries",
                        to="bookkeeping.account",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="intracitysale",
            name="actual_date",
            field=models.DateTimeField(auto_now_add=True, null=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="intracitysale",
            name="ledger_entry",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="intracity_sale",
                to="bookkeeping.ledgerentry",
            ),
        ),
        migrations.AddField(
            model_name="expense",
            name="actual_date",
            field=models.DateTimeField(auto_now_add=True, null=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="expense",
            name="reversed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="charge",
            name="actual_date",
            field=models.DateTimeField(auto_now_add=True, null=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="charge",
            name="reversed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(
            backfill_intracity_sale_ledger_entries,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="intracitysale",
            name="actual_date",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="expense",
            name="actual_date",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="charge",
            name="actual_date",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.RemoveField(
            model_name="intracitysale",
            name="running_balance",
        ),
    ]
