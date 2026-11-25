from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("intracity", "0014_handoverattempt_image_nullable_guard"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "intracity_package" DROP COLUMN IF EXISTS "type";',
        ),
    ]
