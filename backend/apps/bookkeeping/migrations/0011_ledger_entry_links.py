import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def backfill_ledger_entry_links(apps, schema_editor):
    AccountBalance = apps.get_model("bookkeeping", "AccountBalance")
    Charge = apps.get_model("bookkeeping", "Charge")
    Expense = apps.get_model("bookkeeping", "Expense")
    FundsTransfer = apps.get_model("bookkeeping", "FundsTransfer")
    IntracitySale = apps.get_model("bookkeeping", "IntracitySale")
    LedgerEntry = apps.get_model("bookkeeping", "LedgerEntry")
    database = schema_editor.connection.alias

    LedgerEntry.objects.using(database).filter(actual_date__isnull=True).update(
        actual_date=models.F("created_at")
    )

    for sale in IntracitySale.objects.using(database).select_related(
        "ledger_entry"
    ).iterator():
        LedgerEntry.objects.using(database).filter(
            pk=sale.ledger_entry_id
        ).update(actual_date=sale.actual_date, created_at=sale.actual_date)

    for model, transaction_type in ((Expense, "expense"), (Charge, "charge")):
        for item in model.objects.using(database).filter(
            ledger_entry__isnull=True
        ).iterator():
            amount = abs(Decimal(str(item.amount)))
            entry = LedgerEntry.objects.using(database).create(
                account_id=item.account_id,
                entry_type="debit",
                amount=-amount,
                running_balance=Decimal("0.00"),
                transaction_type=transaction_type,
                reference=uuid.uuid4(),
            )
            event_date = item.actual_date or item.added_at
            LedgerEntry.objects.using(database).filter(pk=entry.pk).update(
                actual_date=event_date,
                created_at=event_date,
            )
            model.objects.using(database).filter(pk=item.pk).update(
                ledger_entry_id=entry.pk
            )

    for transfer in FundsTransfer.objects.using(database).filter(
        from_account_ledger_entry__isnull=True,
        to_account_ledger_entry__isnull=True,
    ).iterator():
        amount = abs(Decimal(str(transfer.amount)))
        reference = uuid.uuid4()
        from_entry = LedgerEntry.objects.using(database).create(
            account_id=transfer.from_account_id,
            entry_type="debit",
            amount=-amount,
            running_balance=Decimal("0.00"),
            transaction_type="transfer out",
            reference=reference,
        )
        to_entry = LedgerEntry.objects.using(database).create(
            account_id=transfer.to_account_id,
            entry_type="credit",
            amount=amount,
            running_balance=Decimal("0.00"),
            transaction_type="transfer in",
            reference=reference,
        )
        LedgerEntry.objects.using(database).filter(
            pk__in=[from_entry.pk, to_entry.pk]
        ).update(actual_date=transfer.added_at, created_at=transfer.added_at)
        FundsTransfer.objects.using(database).filter(pk=transfer.pk).update(
            from_account_ledger_entry_id=from_entry.pk,
            to_account_ledger_entry_id=to_entry.pk,
        )

    balances = {}
    entries = LedgerEntry.objects.using(database).order_by(
        "account_id", "actual_date", "pk"
    )
    for entry in entries.iterator():
        balance = balances.get(entry.account_id, Decimal("0.00"))
        balance += Decimal(str(entry.amount))
        LedgerEntry.objects.using(database).filter(pk=entry.pk).update(
            running_balance=balance
        )
        balances[entry.account_id] = balance

    # Keep the legacy snapshots used by existing account transaction views aligned.
    for model in (Expense, Charge):
        for item in model.objects.using(database).select_related(
            "ledger_entry", "running_balance"
        ).iterator():
            if item.running_balance_id:
                AccountBalance.objects.using(database).filter(
                    pk=item.running_balance_id
                ).update(running_balance=item.ledger_entry.running_balance)

    for transfer in FundsTransfer.objects.using(database).select_related(
        "from_account_ledger_entry",
        "to_account_ledger_entry",
        "from_account_running_balance",
        "to_account_running_balance",
    ).iterator():
        if transfer.from_account_running_balance_id:
            AccountBalance.objects.using(database).filter(
                pk=transfer.from_account_running_balance_id
            ).update(
                running_balance=transfer.from_account_ledger_entry.running_balance
            )
        if transfer.to_account_running_balance_id:
            AccountBalance.objects.using(database).filter(
                pk=transfer.to_account_running_balance_id
            ).update(
                running_balance=transfer.to_account_ledger_entry.running_balance
            )


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0010_intracitysale_ledgerentry"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="ledgerentry",
                    name="actual_date",
                    field=models.DateTimeField(auto_now_add=True, null=True),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "bookkeeping_ledgerentry" ADD COLUMN IF NOT EXISTS "actual_date" timestamp with time zone NULL',
                    reverse_sql='ALTER TABLE "bookkeeping_ledgerentry" DROP COLUMN IF EXISTS "actual_date"',
                ),
            ],
        ),
        migrations.AddField(
            model_name="expense",
            name="ledger_entry",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="bookkeeping.ledgerentry",
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="ledger_entry",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="bookkeeping.ledgerentry",
            ),
        ),
        migrations.AddField(
            model_name="fundstransfer",
            name="from_account_ledger_entry",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="transfer_out",
                to="bookkeeping.ledgerentry",
            ),
        ),
        migrations.AddField(
            model_name="fundstransfer",
            name="to_account_ledger_entry",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="transfer_in",
                to="bookkeeping.ledgerentry",
            ),
        ),
        migrations.AlterField(
            model_name="ledgerentry",
            name="transaction_type",
            field=models.CharField(
                choices=[
                    ("sale", "Sale"),
                    ("expense", "Expense"),
                    ("transfer in", "Transfer In"),
                    ("transfer out", "Transfer Out"),
                    ("charge", "Charge"),
                ],
                max_length=255,
            ),
        ),
        migrations.RunPython(
            backfill_ledger_entry_links,
            migrations.RunPython.noop,
        ),
    ]
