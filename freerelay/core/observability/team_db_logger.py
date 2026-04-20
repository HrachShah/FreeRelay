import logging
import subprocess
import json
import uuid
from freerelay.config.settings import get_settings
from freerelay.core.observability.outcome import OutcomeRecord

logger = logging.getLogger("freerelay.usage.team_db")

class TeamDbUsageLogger:
    """Logs token usage and outcomes to the shared team database."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def log(self, record: OutcomeRecord) -> None:
        # We always log to team-db for the MVP if we can
        
        try:
            # Prepare SQL statement
            # Using team-db CLI for sync support
            def escape(val):
                if val is None: return "NULL"
                if isinstance(val, str):
                    return "'" + val.replace("'", "''") + "'"
                return str(val)

            sql = f"""
            INSERT INTO usage_logs (
                id, user_id, org_id, request_id, provider, model, success, 
                latency_ms, tokens, cost, baseline_cost, savings, notes,
                prompt_tokens, completion_tokens
            ) VALUES (
                {escape(str(uuid.uuid4()))}, 
                {escape(record.user_id)}, 
                {escape(record.org_id)}, 
                {escape(record.request_id)}, 
                {escape(record.selected_provider)}, 
                {escape(record.model)}, 
                {1 if record.success else 0}, 
                {record.latency_ms}, 
                {record.cost_tokens}, 
                {record.cost_usd}, 
                {record.baseline_cost_usd}, 
                {record.savings_usd}, 
                {escape(record.notes)},
                {record.tokens_prompt},
                {record.tokens_completion}
            )
            """
            
            logger.info(f"Logging usage to team-db for user {record.user_id}")
            # Execute via team-db CLI
            subprocess.run(["team-db", sql.strip()], capture_output=True, text=True, check=True)
            logger.debug("Successfully logged usage to team-db")
            
        except Exception as e:
            logger.error(f"Failed to log usage to team-db: {e}")
