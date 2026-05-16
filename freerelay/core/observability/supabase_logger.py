import logging

from freerelay.config.settings import get_settings
from freerelay.core.observability.outcome import OutcomeRecord

logger = logging.getLogger("freerelay.usage")

class SupabaseUsageLogger:
    """Logs token usage and outcomes to Supabase."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def log(self, record: OutcomeRecord) -> None:
        if not self.settings.enable_supabase_auth:
            return

        from freerelay.shared.tenancy.supabase import get_supabase_client

        try:
            supabase = get_supabase_client()
            supabase.table("usage_logs").insert({
                "request_id": record.request_id,
                "user_id": record.user_id,
                "provider": record.selected_provider,
                "success": record.success,
                "latency_ms": record.latency_ms,
                "tokens": record.cost_tokens,
                "schema_pass": record.schema_pass,
                "notes": record.notes
            }).execute()
        except (ValueError, TypeError, AttributeError) as e:
            logger.error(f"Failed to log usage to Supabase: {e}")
