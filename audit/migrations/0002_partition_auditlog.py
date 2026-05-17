import django.db.models.deletion
import uuid
import psqlextra.backend.migrations.operations
import psqlextra.manager.manager
import psqlextra.types
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('audit', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Rename existing table
        migrations.RunSQL(
            sql="ALTER TABLE audit_auditlog RENAME TO audit_auditlog_old;",
            reverse_sql="ALTER TABLE audit_auditlog_old RENAME TO audit_auditlog;",
        ),
        # 2. Create partitioned table
        psqlextra.backend.migrations.operations.PostgresCreatePartitionedModel(
            name='AuditLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(max_length=255)),
                ('resource_type', models.CharField(max_length=100)),
                ('resource_id', models.CharField(blank=True, max_length=100, null=True)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
            partitioning_options={
                'method': psqlextra.types.PostgresPartitioningMethod.RANGE,
                'key': ['created_at'],
            },
            bases=(psqlextra.models.PostgresPartitionedModel,),
            managers=[
                ('objects', psqlextra.manager.manager.PostgresManager()),
            ],
        ),
        # 3. Create initial partitions (Current and Next month)
        psqlextra.backend.migrations.operations.PostgresAddDefaultPartition(
            model_name='AuditLog',
            name='default',
        ),
        # 4. Copy data from old to new
        migrations.RunSQL(
            sql="INSERT INTO audit_auditlog (id, action, resource_type, resource_id, details, ip_address, created_at, user_id) SELECT id, action, resource_type, resource_id, details, ip_address, created_at, user_id FROM audit_auditlog_old;",
            reverse_sql="INSERT INTO audit_auditlog_old (id, action, resource_type, resource_id, details, ip_address, created_at, user_id) SELECT id, action, resource_type, resource_id, details, ip_address, created_at, user_id FROM audit_auditlog;",
        ),
        # 5. Drop old table
        migrations.RunSQL(
            sql="DROP TABLE audit_auditlog_old;",
            reverse_sql="",
        ),
    ]
