from django.utils.module_loading import import_string

class LazyPartitioningManager:
    """Lazy loader for the partitioning manager to avoid AppRegistryNotReady errors
    during Django startup/settings loading.
    """
    _manager = None

    def _load(self):
        if self._manager is None:
            from psqlextra.partitioning import (
                PostgresPartitioningConfig,
                PostgresPartitioningManager,
                PostgresTimePartitionSize,
                PostgresCurrentTimePartitioningStrategy,
            )
            from audit.models import AuditLog
            from payments.models import WalletTransaction

            self._manager = PostgresPartitioningManager([
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
        return self._manager

    def plan(self, **kwargs):
        return self._load().plan(**kwargs)

    def apply(self, **kwargs):
        return self._load().apply(**kwargs)

manager = LazyPartitioningManager()
