
import uuid
from freerelay.core.observability.outcome import OutcomeRecord
from freerelay.core.observability.team_db_logger import TeamDbUsageLogger

logger = TeamDbUsageLogger()
record = OutcomeRecord(
    request_id="test_req",
    user_id="e6567d8b-ceae-4dc4-a196-d91b222d2a9d",
    selected_provider="test_provider",
    model="test_model",
    alternatives=[],
    success=True,
    schema_pass=True,
    latency_ms=100.0,
    cost_tokens=10,
    cost_usd=0.001,
    baseline_cost_usd=0.002,
    savings_usd=0.001,
    hallucination_signal=0.0,
    downstream_success=None,
    notes="test note"
)
print("Logging record...")
logger.log(record)
print("Done.")
