# Generated manually to add missing secret_code column to interactions_appointment

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interactions', '0012_dispute_evidence'),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE interactions_appointment ADD COLUMN IF NOT EXISTS secret_code varchar(6) NULL;',
            state_operations=[
                migrations.AddField(
                    model_name='appointment',
                    name='secret_code',
                    field=models.CharField(blank=True, max_length=6, null=True),
                ),
            ]
        ),
    ]
