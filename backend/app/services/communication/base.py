"""Communication Adapter abstraction — Sprint 3.

A CommunicationAdapter is the one shape every delivery channel (Gmail
today, WhatsApp next) implements. `notification_service.send()` (Sprint
1's channel-agnostic dispatch surface — see that module's docstring)
resolves a notification's channel to an adapter via
`communication.get_adapter()` and calls its `.send()`, instead of knowing
anything about Gmail, WhatsApp, or SMTP itself. That's what makes Sprint
1's "channel-agnostic" description literally true rather than aspirational.

This is a `typing.Protocol` (structural typing), not an abstract base
class: an adapter doesn't need to inherit from anything, it only needs a
`channel` attribute and `is_configured()`/`send()` methods with this
shape — matching every other service module in this project, none of
which use class inheritance either (see e.g. order_service.py,
notification_service.py itself). A plain module with a module-level
`channel` variable and two module-level functions already satisfies this
Protocol structurally; see gmail_adapter.py.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DeliveryResult:
    """The outcome of one adapter.send() call — channel-agnostic, so
    notification_service never needs to know Gmail's or WhatsApp's own
    result/error shape.
    """

    success: bool
    provider_message_id: str | None = None
    error: str | None = None


@runtime_checkable
class CommunicationAdapter(Protocol):
    """The shape every delivery channel adapter must have.

    channel: the value that goes in `notifications.channel` once this
        adapter handles a send (e.g. "email", "whatsapp").
    is_configured(): True if real credentials are present. When False,
        notification_service.send() falls back to its original
        nothing-actually-delivered stub instead of calling send() at all
        — see that function's docstring for why that distinction (not
        registered vs. registered-but-unconfigured) matters.
    send(): attempt real delivery. Must never raise — a delivery failure
        (bad recipient, provider error, timeout) is reported through
        DeliveryResult.success/error, not an exception, so
        notification_service.send() can transition the notification to
        "failed" cleanly instead of the whole request blowing up.
    """

    channel: str

    def is_configured(self) -> bool: ...

    def send(self, notification: dict) -> DeliveryResult: ...
