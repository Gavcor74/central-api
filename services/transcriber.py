from __future__ import annotations

import os


def get_transcriber_config() -> dict[str, object]:
    provider = os.getenv('TRANSCRIBER_PROVIDER', '').strip()
    model = os.getenv('TRANSCRIBER_MODEL', '').strip()
    api_key = os.getenv('TRANSCRIBER_API_KEY', '').strip()
    return {
        'enabled': bool(provider),
        'provider': provider or None,
        'model': model or None,
        'has_api_key': bool(api_key),
    }
