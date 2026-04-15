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


def get_openclaw_plan() -> dict[str, object]:
    config = get_openclaw_config()
    if config['enabled']:
        recommended_mode = 'vps_gateway'
        next_steps = [
            'OpenClaw ya puede apuntar a tu VPS.',
            'Mantén Ollama en la URL interna que ya validaste.',
            'Cuando quieras, conectamos canales y automatizaciones encima.',
        ]
    else:
        recommended_mode = 'needs_configuration'
        next_steps = [
            'Configura OPENCLAW_BASE_URL en EasyPanel.',
            'Decide si OpenClaw vivira en el VPS o se usara solo como gateway externo.',
            'Cuando el base_url exista, podras conectarlo al resto del sistema.',
        ]

    return {
        'enabled': config['enabled'],
        'base_url': config['base_url'],
        'has_api_key': config['has_api_key'],
        'recommended_mode': recommended_mode,
        'next_steps': next_steps,
    }
