import os
import django
from datetime import datetime, timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ns_backend.settings')
django.setup()

from psqlextra.partitioning import (
    PostgresPartitioningConfig,
    PostgresPartitioningManager,
    PostgresTimePartitionSize,
    PostgresCurrentTimePartitioningStrategy,
)
from audit.models import AuditLog
from payments.models import WalletTransaction

manager = PostgresPartitioningManager([
    PostgresPartitioningConfig(
        model=AuditLog,
        strategy=PostgresCurrentTimePartitioningStrategy(
            size=PostgresTimePartitionSize(months=1),
            count=6,
        ),
    ),
    PostgresPartitioningConfig(
        model=WalletTransaction,
        strategy=PostgresCurrentTimePartitioningStrategy(
            size=PostgresTimePartitionSize(months=1),
            count=6,
        ),
    ),
])

print("Planning partitions...")
plan = manager.plan()
plan.print()
print("Applying partitions...")
plan.apply()
print("Partitions created successfully.")
