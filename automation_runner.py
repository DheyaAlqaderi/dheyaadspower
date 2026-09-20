"""
Automation Runner - Unified entrypoint and backward-compatibility interface.
All core platform implementations have been modularized into the `automations/` package:
- `automations.instagram`: InstagramWorker & InstagramDatabaseManager
- `automations.facebook`: FacebookWorker
- `automations.twitter`: TwitterWorker (X)
- `automations.tiktok`: TikTokWorker
- `automations.base`: BaseAutomationWorker & AutomationWorker
- `automations.hub`: MultiPlatformAutomationHub
"""

from automations import (
    BaseAutomationWorker,
    AutomationWorker,
    InstagramWorker,
    InstagramDatabaseManager,
    FacebookWorker,
    TwitterWorker,
    TikTokWorker,
    MultiPlatformAutomationHub,
    get_worker_class,
    WORKER_REGISTRY,
    PROCESSED_LOG_FILE,
    INSTA_DATABASE_FILE,
)

__all__ = [
    "BaseAutomationWorker",
    "AutomationWorker",
    "InstagramWorker",
    "InstagramDatabaseManager",
    "FacebookWorker",
    "TwitterWorker",
    "TikTokWorker",
    "MultiPlatformAutomationHub",
    "get_worker_class",
    "WORKER_REGISTRY",
    "PROCESSED_LOG_FILE",
    "INSTA_DATABASE_FILE",
]
