"""Communication Adapter registry — Sprint 3, extended in Sprint 4, and
again for the Twilio WhatsApp Sandbox integration.

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

Two independently complete adapters now exist for that same "whatsapp"
channel — Meta's Cloud API (whatsapp_adapter.py) and Twilio's WhatsApp
Sandbox (twilio_whatsapp_adapter.py, this project's actual university/demo
setup) — so which one is *selected* needs to be an explicit, testable
decision rather than whichever `register_adapter()` call happens to run
last silently overwriting the other. See `_register_whatsapp_provider()`.
"""

from app.services.communication import gmail_adapter, twilio_whatsapp_adapter, whatsapp_adapter
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


def _register_whatsapp_provider() -> None:
    """Exactly one of Twilio (Sandbox — this project's actual, current
    setup) or Meta (Cloud API — provisioned separately, currently dark;
    see docs/) occupies the "whatsapp" channel at a time. Twilio wins only
    when it's actually configured; **Meta is the default in every other
    case, configured or not** — deliberately preserving this project's
    pre-Twilio invariant that `get_adapter("whatsapp")` always returns a
    real adapter object, registered-but-possibly-unconfigured, exactly
    like it did before this function existed (see
    test_whatsapp_adapter_registered_under_its_own_channel, unchanged).
    `_dispatch()` already treats "not registered" and "registered but
    unconfigured" identically (falls back to the stub either way — see
    its own docstring), so this costs nothing functionally while keeping
    every existing Meta-path test and behavior exactly as it was.

    A function, not bare module-level statements, specifically so this
    precedence is independently callable and testable with different
    is_configured() states — see test_communication_adapters.py's
    registry-precedence tests (Twilio only / Meta only / both / neither).
    """
    if twilio_whatsapp_adapter.is_configured():
        register_adapter(twilio_whatsapp_adapter)
    else:
        register_adapter(whatsapp_adapter)


register_adapter(gmail_adapter)
_register_whatsapp_provider()


def whatsapp_status() -> dict:
    """Which WhatsApp provider (if any) is actually live right now, for
    the Communications Workspace's status indicator — the one place the
    frontend needs to tell the difference between "off", "Twilio Sandbox
    (test environment, not a real business number)", and "Meta Cloud
    API", rather than a generic on/off toggle that could let a Sandbox
    test session look like a real WhatsApp Business connection.

    Checks the registered adapter's own is_configured(), not just which
    object `get_adapter("whatsapp")` happens to return — Meta is always
    the registered *object* when Twilio isn't configured (see
    `_register_whatsapp_provider`'s own docstring on why), but that
    doesn't mean it's actually configured; this reports the true, honest
    "is WhatsApp actually reachable right now" signal the UI needs.

    Never raises, never reads a secret value — `sandboxNumber` is Twilio's
    own publicly-documented shared Sandbox number (see
    twilio_whatsapp_adapter.SANDBOX_FROM_NUMBER's own docstring), not a
    credential.
    """
    adapter = get_adapter("whatsapp")
    if adapter is twilio_whatsapp_adapter and adapter.is_configured():
        return {
            "configured": True,
            "provider": "twilio_sandbox",
            "sandboxNumber": twilio_whatsapp_adapter.SANDBOX_FROM_NUMBER.removeprefix("whatsapp:"),
        }
    if adapter is whatsapp_adapter and adapter.is_configured():
        return {"configured": True, "provider": "meta", "sandboxNumber": None}
    return {"configured": False, "provider": None, "sandboxNumber": None}
