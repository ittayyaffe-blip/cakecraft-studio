from supabase import create_client, Client

from app.core.config import settings

# Module-level client: created once on first import, reused everywhere else
# that imports it. That's the singleton — no extra wrapper needed.
supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
