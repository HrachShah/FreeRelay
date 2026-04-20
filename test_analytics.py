import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from freerelay.observability.analytics import get_usage_analytics

try:
    analytics = get_usage_analytics()
    print("Analytics successful:")
    print(analytics.model_dump_json(indent=2))
except Exception as e:
    print(f"Analytics failed: {e}")
