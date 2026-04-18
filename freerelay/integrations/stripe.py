from typing import Any

import stripe  # type: ignore

from freerelay.config.settings import get_settings


def create_checkout_session(customer_email: str, price_id: str) -> Any:
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key
    
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price': price_id,
            'quantity': 1,
        }],
        mode='subscription',
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        customer_email=customer_email,
    )
    return session
