"""Communication Adapter registry — Sprint 3, extended in Sprint 4.

The one place `notification_service.send()` asks "which adapter handles
this channel?" without importing a specific channel module itself.
`whatsapp_adapter` (Sprint 4) registers itself the exact same way
`gmail_adapter` (Sprint 3) does below — proof that "the entire integration
a new channel needs to plug into the existing, unmodified approval
workflow" was a real claim, not just documentation: adding WhatsApp
required zero changes to notification_service.py, admin/notifications.py,
or the frontend's notification queue/drawer (which already renders
whatever `channel` string a notification ends up with generically). See
docs/SPRINT4_WHATSAPP_ADAPTER.md.
"""

from app.services.communication import gmail_adapter, whatsapp_adapter
from app.services.communication.base import CommunicationAdapter, DeliveryResult

DEFAULT_CHANNEL = "email"

_ADAPTERS: dict[str, CommunicationAdapter] = {}


def register_adapter(adapter: CommunicationAdapter) -> None:
    """Register a channel adapter. Validated against the
    CommunicationAdapter shape at registration time (not just hoped for)
    so a malformed future adapter fails loudly here, at import time,
    rather than silently the first time a notification tries to use it.
    """
    if not isinstance(adapter, CommunicationAdapter):
        raise TypeError(
            f"{adapter!r} does not satisfy the CommunicationAdapter protocol "
            "(needs a `channel` attribute plus is_configured()/send() functions)"
        )
    _ADAPTERS[adapter.channel] = adapter


def get_adapter(channel: str) -> CommunicationAdapter | None:
    """The adapter registered for one channel, or None if nothing is
    registered for it. notification_service.send() treats "nothing
    registered" and "registered but not configured" the same way (fall
    back to the stub) — see its docstring.
    """
    return _ADAPTERS.get(channel)


register_adapter(gmail_adapter)
register_adapter(whatsapp_adapter)
