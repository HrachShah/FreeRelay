"""
FreeRelay — Stripe Metered Usage Pipeline
=========================================
Aggregates and syncs usage data to Stripe.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time

import stripe

from freerelay.config.settings import get_settings

logger = logging.getLogger("freerelay.billing.stripe")


async def stripe_billing_worker() -> None:
    """
    Background worker that periodically syncs usage to Stripe.
    """
    settings = get_settings()
    if not settings.stripe_secret_key:
        logger.warning("Stripe secret key not set. Billing worker disabled.")
        return

    stripe.api_key = settings.stripe_secret_key
    logger.info("Starting Stripe billing worker...")

    while True:
        try:
            await sync_usage_to_stripe()
        except Exception as e:
            logger.exception("Error in stripe billing sync")
        
        # Sync every 5 minutes for MVP
        await asyncio.sleep(300)


async def sync_usage_to_stripe() -> None:
    """
    Finds unreported usage logs and reports them to Stripe subscription items.
    """
    # 1. Get all organizations with a stripe_subscription_item_id
    sql_orgs = "SELECT id, stripe_subscription_item_id FROM organizations WHERE stripe_subscription_item_id IS NOT NULL"
    try:
        result_orgs = subprocess.run(
            ["team-db", sql_orgs.strip()], 
            capture_output=True, 
            text=True, 
            check=True
        )
        orgs = json.loads(result_orgs.stdout)
    except Exception as e:
        logger.error(f"Failed to fetch organizations for billing: {e}")
        return

    for org in orgs:
        org_id = org["id"]
        si_id = org["stripe_subscription_item_id"]

        # 2. Sum up unreported usage for this org
        sql_usage = f"""
        SELECT 
            SUM(tokens) as total_tokens, 
            GROUP_CONCAT(id) as ids 
        FROM usage_logs 
        WHERE org_id = '{org_id}' AND reported_to_stripe = 0
        """
        try:
            result_usage = subprocess.run(
                ["team-db", sql_usage.strip()], 
                capture_output=True, 
                text=True, 
                check=True
            )
            usage_data = json.loads(result_usage.stdout)
        except Exception as e:
            logger.error(f"Failed to fetch usage for org {org_id}: {e}")
            continue

        if usage_data and usage_data[0] and usage_data[0].get("total_tokens"):
            total_tokens = usage_data[0]["total_tokens"]
            log_ids = usage_data[0]["ids"].split(",")

            try:
                # 3. Report to Stripe
                # We use 'tokens' as the quantity.
                stripe.UsageRecord.create(
                    quantity=total_tokens,
                    subscription_item=si_id,
                    timestamp=int(time.time()),
                    action="increment",
                )

                # 4. Mark as reported
                for log_id in log_ids:
                    sql_update = f"UPDATE usage_logs SET reported_to_stripe = 1 WHERE id = '{log_id}'"
                    subprocess.run(["team-db", sql_update], check=True, capture_output=True)
                
                logger.info(f"Reported {total_tokens} tokens for org {org_id} to Stripe.")
            except Exception as e:
                logger.error(f"Failed to report usage for org {org_id} to Stripe: {e}")
