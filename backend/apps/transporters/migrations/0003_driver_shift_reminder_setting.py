from django.db import migrations, models


def seed_setting(apps, schema_editor):
    apps.get_model('transporters', 'DriverShiftReminderSetting').objects.create(
        pk=1, minutes_before_close=30
    )


class Migration(migrations.Migration):
    dependencies = [('transporters', '0002_driver_shifts')]

    operations = [
        migrations.CreateModel(name='DriverShiftReminderSetting', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('minutes_before_close', models.PositiveSmallIntegerField(default=30)),
        ]),
        migrations.RunPython(seed_setting, migrations.RunPython.noop),
    ]
