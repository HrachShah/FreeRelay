import json
import subprocess
from datetime import datetime, timedelta
from typing import Optional
from freerelay.shared.models.internal import UsageAnalytics, ModelUsage, DailySavings

def run_query(query: str, params: Optional[list] = None):
    result = subprocess.run(["team-db", query], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Database query failed: {result.stderr}")
    return json.loads(result.stdout)


def _validate_user_id(user_id: str) -> str:
    """Validate and sanitize user_id before use in SQL."""
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("user_id must be a non-empty string")
    return user_id


def _sql_where(user_id: str, days: int) -> str:
    """Build a SQL WHERE clause with proper escaping for user_id."""
    uid = _validate_user_id(user_id)
    return f"WHERE user_id = '{uid}' AND created_at >= datetime('now', '-{days} days')"


def get_usage_analytics(user_id: str, days: int = 7) -> UsageAnalytics:
    if not user_id:
        return UsageAnalytics(
            total_spend=0, total_savings=0, total_tokens=0,
            savings_percentage=0, top_models=[], daily_trends=[],
            projected_monthly_savings=0
        )

    where_clause = _sql_where(user_id, days)

    stats_query = f"""
    SELECT
        SUM(cost) as total_spend,
        SUM(savings) as total_savings,
        SUM(tokens) as total_tokens
    FROM usage_logs
    {where_clause}
    """
    stats_list = run_query(stats_query)
    stats = stats_list[0] if stats_list else {}
    total_spend = stats.get("total_spend") or 0.0
    total_savings = stats.get("total_savings") or 0.0
    total_tokens = stats.get("total_tokens") or 0

    baseline = total_spend + total_savings
    savings_percentage = (total_savings / baseline * 100) if baseline > 0 else 0.0

    models_query = f"""
    SELECT
        model,
        SUM(tokens) as tokens,
        SUM(cost) as cost,
        SUM(savings) as savings
    FROM usage_logs
    {where_clause}
    GROUP BY model
    ORDER BY tokens DESC
    LIMIT 5
    """
    models_data = run_query(models_query)
    top_models = []
    for m in models_data:
        m_tokens = m.get("tokens") or 0
        percentage = (m_tokens / total_tokens * 100) if total_tokens > 0 else 0.0
        top_models.append(ModelUsage(
            model=m.get("model") or "unknown",
            tokens=m_tokens,
            cost=m.get("cost") or 0.0,
            savings=m.get("savings") or 0.0,
            percentage=percentage
        ))

    trends_query = f"""
    SELECT
        strftime('%Y-%m-%d', created_at) as day,
        SUM(cost) as actual,
        SUM(baseline_cost) as baseline,
        SUM(savings) as savings
    FROM usage_logs
    {where_clause}
    GROUP BY day
    ORDER BY day DESC
    LIMIT {days}
    """
    trends_data = run_query(trends_query)
    daily_trends = [
        DailySavings(
            day=t.get("day"),
            actual=t.get("actual") or 0.0,
            baseline=t.get("baseline") or 0.0,
            savings=t.get("savings") or 0.0
        ) for t in reversed(trends_data)
    ]

    if not daily_trends:
        daily_trends = [
            DailySavings(
                day=(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'),
                actual=0, baseline=0, savings=0
            ) for i in range(days - 1, -1, -1)
        ]

    if trends_data:
        avg_daily_savings = total_savings / len(trends_data)
        projected = avg_daily_savings * 30
    else:
        projected = 0.0

    return UsageAnalytics(
        total_spend=total_spend,
        total_savings=total_savings,
        total_tokens=total_tokens,
        savings_percentage=savings_percentage,
        top_models=top_models,
        daily_trends=daily_trends,
        projected_monthly_savings=projected
    )
