from supabase import ClientOptions, create_client, Client

from app.core.config import settings

# Module-level client: created once on first import, reused everywhere else
# that imports it. That's the singleton — no extra wrapper needed.
#
# postgrest_client_timeout: the library's own default is 120s (confirmed
# via introspection, not assumed) -- on a slow/stalled query or connection
# hiccup, every one of this project's request handlers would otherwise
# wait up to two minutes before failing. A real production /orders/{id}/pay
# call was observed taking 74s end to end with zero Claude calls involved
# (see payment_service.py's own docstring) -- this bounds any single
# Postgrest call to a customer-latency-appropriate ceiling instead, so a
# stalled call now fails fast and the existing idempotent retry path
# (payment_service.simulate_payment, or simply asking again in chat)
# recovers quickly rather than the customer watching a frozen screen.
supabase: Client = create_client(
    settings.supabase_url, settings.supabase_key, options=ClientOptions(postgrest_client_timeout=15)
)
