import django.db.models.deletion
import psqlextra.backend.migrations.operations
import psqlextra.manager.manager
import psqlextra.types
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0005_subscriptionplan_interval_subscriptionplan_tier'),
    ]

    operations = [
        # 1. Rename existing table
        migrations.RunSQL(
            sql="ALTER TABLE payments_wallettransaction RENAME TO payments_wallettransaction_old;",
            reverse_sql="ALTER TABLE payments_wallettransaction_old RENAME TO payments_wallettransaction;",
        ),
        # 2. Create partitioned table
        psqlextra.backend.migrations.operations.PostgresCreatePartitionedModel(
            name='WalletTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('transaction_type', models.CharField(choices=[('CREDIT', 'Credit'), ('DEBIT', 'Debit')], max_length=10)),
                ('description', models.CharField(max_length=255)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed')], default='COMPLETED', max_length=20)),
                ('reference_id', models.CharField(blank=True, max_length=100, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('wallet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='payments.wallet')),
            ],
            partitioning_options={
                'method': psqlextra.types.PostgresPartitioningMethod.RANGE,
                'key': ['created_at'],
            },
            bases=(psqlextra.models.PostgresPartitionedModel,),
            managers=[
                ('objects', psqlextra.manager.manager.PostgresManager()),
            ],
        ),
        # 3. Create initial partitions
        psqlextra.backend.migrations.operations.PostgresAddDefaultPartition(
            model_name='WalletTransaction',
            name='default',
        ),
        # 4. Copy data
        migrations.RunSQL(
            sql="INSERT INTO payments_wallettransaction (id, amount, transaction_type, description, status, reference_id, created_at, wallet_id) SELECT id, amount, transaction_type, description, status, reference_id, created_at, wallet_id FROM payments_wallettransaction_old;",
            reverse_sql="INSERT INTO payments_wallettransaction_old (id, amount, transaction_type, description, status, reference_id, created_at, wallet_id) SELECT id, amount, transaction_type, description, status, reference_id, created_at, wallet_id FROM payments_wallettransaction;",
        ),
        # 5. Drop old table
        migrations.RunSQL(
            sql="DROP TABLE payments_wallettransaction_old;",
            reverse_sql="",
        ),
    ]
