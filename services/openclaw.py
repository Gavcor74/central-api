from __future__ import annotations

import os


def get_openclaw_config() -> dict[str, object]:
    base_url = os.getenv('OPENCLAW_BASE_URL', '').strip()
    api_key = os.getenv('OPENCLAW_API_KEY', '').strip()
    return {
        'enabled': bool(base_url),
        'base_url': base_url or None,
        'has_api_key': bool(api_key),
    }
