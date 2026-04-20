"""
FreeRelay — Usage Analytics
============================
Aggregates and exposes usage data for organizations.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from freerelay.shared.models.internal import (
    DailySavings,
    ModelUsage,
    UsageAnalytics,
    RequestLogEntry,
    RequestLogResponse,
)

logger = logging.getLogger("freerelay.analytics")


def get_request_logs(
    org_id: str,
    limit: int = 20,
    offset: int = 0,
    model: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> RequestLogResponse:
    """
    Get detailed request logs for an organization with pagination and filtering.
    """
    def escape(val):
        if val is None: return "NULL"
        if isinstance(val, str):
            return "'" + val.replace("'", "''") + "'"
        return str(val)

    try:
        where_clauses = [f"org_id = {escape(org_id)}"]
        if model:
            where_clauses.append(f"model = {escape(model)}")
        if start_date:
            where_clauses.append(f"created_at >= {escape(start_date)}")
        if end_date:
            where_clauses.append(f"created_at <= {escape(end_date)}")
        
        where_sql = " AND ".join(where_clauses)
        
        # 1. Get total count
        sql_count = f"SELECT COUNT(*) as total FROM usage_logs WHERE {where_sql}"
        result_count = subprocess.run(
            ["team-db", sql_count.strip()], 
            capture_output=True, 
            text=True, 
            check=True
        )
        data_count = json.loads(result_count.stdout)
        total = data_count[0]["total"] if data_count else 0
        
        # 2. Get logs
        sql_logs = f"""
        SELECT 
            id, request_id, created_at as timestamp, model, provider, success,
            latency_ms, tokens, prompt_tokens, completion_tokens, cost, savings, 
            notes as decision_reason
        FROM usage_logs 
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT {limit} OFFSET {offset}
        """
        result_logs = subprocess.run(
            ["team-db", sql_logs.strip()], 
            capture_output=True, 
            text=True, 
            check=True
        )
        data_logs = json.loads(result_logs.stdout)
        
        items = [
            RequestLogEntry(
                id=row["id"],
                request_id=row["request_id"],
                timestamp=row["timestamp"],
                model=row["model"] or "unknown",
                provider=row["provider"],
                success=bool(row["success"]),
                latency_ms=row["latency_ms"] or 0.0,
                tokens=row["tokens"] or 0,
                prompt_tokens=row["prompt_tokens"] or 0,
                completion_tokens=row["completion_tokens"] or 0,
                cost=row["cost"] or 0.0,
                savings=row["savings"] or 0.0,
                decision_reason=row["decision_reason"]
            )
            for row in data_logs
        ]
        
        return RequestLogResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error(f"Failed to get request logs for org {org_id}: {e}")
        return RequestLogResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset
        )


def get_usage_analytics(org_id: str) -> UsageAnalytics:
    """
    Get aggregated usage statistics for an organization.
    """
    def escape(val):
        if val is None: return "NULL"
        if isinstance(val, str):
            return "'" + val.replace("'", "''") + "'"
        return str(val)

    try:
        # 1. Total spend and savings
        sql_totals = f"""
        SELECT 
            SUM(cost) as total_spend, 
            SUM(savings) as total_savings 
        FROM usage_logs 
        WHERE org_id = {escape(org_id)}
        """
        result_totals = subprocess.run(
            ["team-db", sql_totals.strip()], 
            capture_output=True, 
            text=True, 
            check=True
        )
        data_totals = json.loads(result_totals.stdout)
        
        total_spend = 0.0
        total_savings = 0.0
        if data_totals and data_totals[0]:
            total_spend = data_totals[0].get("total_spend") or 0.0
            total_savings = data_totals[0].get("total_savings") or 0.0
        
        # 2. Model breakdown
        sql_models = f"""
        SELECT 
            model, 
            COUNT(*) as request_count, 
            SUM(tokens) as total_tokens, 
            SUM(cost) as total_cost, 
            SUM(savings) as total_savings 
        FROM usage_logs 
        WHERE org_id = {escape(org_id)}
        GROUP BY model
        """
        result_models = subprocess.run(
            ["team-db", sql_models.strip()], 
            capture_output=True, 
            text=True, 
            check=True
        )
        data_models = json.loads(result_models.stdout)
        
        model_breakdown = [
            ModelUsage(
                model=row["model"] or "unknown",
                request_count=row["request_count"],
                total_tokens=row["total_tokens"] or 0,
                total_cost=row["total_cost"] or 0.0,
                total_savings=row["total_savings"] or 0.0
            )
            for row in data_models
        ]
        
        # 3. Savings trend (last 30 days)
        sql_trend = f"""
        SELECT 
            strftime('%Y-%m-%d', created_at) as date, 
            SUM(savings) as savings 
        FROM usage_logs 
        WHERE org_id = {escape(org_id)} AND created_at >= date('now', '-30 days')
        GROUP BY date
        ORDER BY date ASC
        """
        result_trend = subprocess.run(
            ["team-db", sql_trend.strip()], 
            capture_output=True, 
            text=True, 
            check=True
        )
        data_trend = json.loads(result_trend.stdout)
        
        savings_trend = [
            DailySavings(
                date=row["date"],
                savings=row["savings"] or 0.0
            )
            for row in data_trend
        ]
        
        return UsageAnalytics(
            total_spend=total_spend,
            total_savings=total_savings,
            model_breakdown=model_breakdown,
            savings_trend=savings_trend
        )
    except Exception as e:
        logger.error(f"Failed to get analytics for org {org_id}: {e}")
        return UsageAnalytics(
            total_spend=0.0,
            total_savings=0.0,
            model_breakdown=[],
            savings_trend=[]
        )
