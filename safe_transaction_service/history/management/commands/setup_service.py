from dataclasses import dataclass
from numbers import Number
from typing import Dict, List, Sequence, Tuple

from django.conf import settings
from django.core.management.base import BaseCommand

from django_celery_beat.models import IntervalSchedule, PeriodicTask

from gnosis.eth import EthereumClientProvider
from gnosis.eth.ethereum_client import EthereumNetwork

from ...models import ProxyFactory, SafeMasterCopy


@dataclass
class CeleryTaskConfiguration:
    name: str
    description: str
    interval: int
    period: str
    enabled: bool = True

    def create_task(self) -> Tuple[PeriodicTask, bool]:
        interval_schedule, _ = IntervalSchedule.objects.get_or_create(
            every=self.interval, period=self.period
        )
        periodic_task, created = PeriodicTask.objects.get_or_create(
            task=self.name,
            defaults={
                "name": self.description,
                "interval": interval_schedule,
                "enabled": self.enabled,
            },
        )
        if not created:
            periodic_task.name = self.description
            periodic_task.interval = interval_schedule
            periodic_task.enabled = self.enabled
            periodic_task.save()

        return periodic_task, created


TASKS = [
    CeleryTaskConfiguration(
        "safe_transaction_service.history.tasks.check_reorgs_task",
        "Check Reorgs",
        3,
        IntervalSchedule.MINUTES,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.history.tasks.check_sync_status_task",
        "Check Sync status",
        10,
        IntervalSchedule.MINUTES,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.history.tasks.index_internal_txs_task",
        "Index Internal Txs",
        13,
        IntervalSchedule.SECONDS,
        enabled=not settings.ETH_L2_NETWORK,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.history.tasks.index_safe_events_task",
        "Index Safe events (L2)",
        13,
        IntervalSchedule.SECONDS,
        enabled=settings.ETH_L2_NETWORK,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.history.tasks.index_new_proxies_task",
        "Index new Proxies",
        15,
        IntervalSchedule.SECONDS,
        enabled=settings.ETH_L2_NETWORK,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.history.tasks.index_erc20_events_task",
        "Index ERC20/721 Events",
        14,
        IntervalSchedule.SECONDS,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.history.tasks.index_erc20_events_out_of_sync_task",
        "Index out of sync ERC20/ERC721 Events",
        5,
        IntervalSchedule.MINUTES,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.history.tasks.reindex_last_hours_task",
        "Reindex master copies for the last hours",
        110,
        IntervalSchedule.MINUTES,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.history.tasks.process_decoded_internal_txs_task",
        "Process Internal Txs",
        20,
        IntervalSchedule.MINUTES,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.contracts.tasks.create_missing_contracts_with_metadata_task",
        "Index contract names and ABIs",
        1,
        IntervalSchedule.HOURS,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.contracts.tasks.reindex_contracts_without_metadata_task",
        "Reindex contracts with missing names or ABIs",
        7,
        IntervalSchedule.DAYS,
    ),
    CeleryTaskConfiguration(
        "safe_transaction_service.tokens.tasks.fix_pool_tokens_task",
        "Fix Pool Token Names",
        1,
        IntervalSchedule.HOURS,
    ),
]

class Command(BaseCommand):
    help = "Setup Transaction Service Required Tasks"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Removing old tasks"))
        PeriodicTask.objects.filter(
            task__startswith="safe_transaction_service"
        ).delete()
        self.stdout.write(self.style.SUCCESS("Old tasks were removed"))

        for task in TASKS:
            _, created = task.create_task()
            if created:
                self.stdout.write(
                    self.style.SUCCESS("Created Periodic Task %s" % task.name)
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS("Task %s was already created" % task.name)
                )

        self.stdout.write(self.style.SUCCESS("Setting up Safe Contract Addresses :) "))

        self._setup_safe_master_copies([
            ("0xaCDd50B5262216a719eb457f4fe08EF3f5aae0aC", 106941, "1.3.0+L2"),
            ("0x994deC611656275Bd52868f77e4484b10Ed6F642", 106942, "1.3.0"),
        ])
        self._setup_safe_proxy_factories([("0x81aC261f72052EFE69D76E3FF8C2a8163fbB7EB3", 106938)])
            

        self.stdout.write(
            self.style.WARNING("Setup manually stuff.")
        )
            

    def _setup_safe_master_copies(
        self, safe_master_copies: Sequence[Tuple[str, int, str]]
    ):
        for address, initial_block_number, version in safe_master_copies:
            safe_master_copy, _ = SafeMasterCopy.objects.get_or_create(
                address=address,
                defaults={
                    "initial_block_number": initial_block_number,
                    "tx_block_number": initial_block_number,
                    "version": version,
                    "l2": version.endswith("+L2"),
                },
            )
            if (
                safe_master_copy.version != version
                or safe_master_copy.initial_block_number != initial_block_number
            ):
                safe_master_copy.version = initial_block_number
                safe_master_copy.version = version
                safe_master_copy.save(update_fields=["initial_block_number", "version"])

    def _setup_safe_proxy_factories(
        self, safe_proxy_factories: Sequence[Tuple[str, int]]
    ):
        for address, initial_block_number in safe_proxy_factories:
            ProxyFactory.objects.get_or_create(
                address=address,
                defaults={
                    "initial_block_number": initial_block_number,
                    "tx_block_number": initial_block_number,
                },
            )
