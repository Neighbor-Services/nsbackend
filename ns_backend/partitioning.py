from psqlextra.partitioning import (
    PostgresPartitioningConfig,
    PostgresPartitioningManager,
    PostgresTimePartitionSize,
    PostgresTimePartitioningStrategy,
)

manager = PostgresPartitioningManager([
    PostgresPartitioningConfig(
        model='audit.AuditLog',
        strategy=PostgresTimePartitioningStrategy(
            size=PostgresTimePartitionSize.MONTH,
            count=6,
        ),
    ),
    PostgresPartitioningConfig(
        model='payments.WalletTransaction',
        strategy=PostgresTimePartitioningStrategy(
            size=PostgresTimePartitionSize.MONTH,
            count=6,
        ),
    ),
])
