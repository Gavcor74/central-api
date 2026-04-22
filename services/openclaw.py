from __future__ import annotations

import os


def get_openclaw_config() -> dict[str, object]:
    base_url = os.getenv('OPENCLAW_BASE_URL', '').strip()
    api_key = os.getenv('OPENCLAW_API_KEY', '').strip()
    api_central_url = os.getenv('API_CENTRAL_URL', '').strip()
    return {
        'enabled': bool(base_url),
        'base_url': base_url or None,
        'has_api_key': bool(api_key),
        'api_central_url': api_central_url or None,
    }


def get_openclaw_plan() -> dict[str, object]:
    config = get_openclaw_config()
    if config['enabled']:
        recommended_mode = 'vps_gateway'
        next_steps = [
            'Conecta OpenClaw a API CENTRAL como cerebro de decisión.',
            'Mantén Ollama en la URL interna que ya validaste.',
            'Usa OpenClaw solo para ejecutar acciones aprobadas.',
        ]
    else:
        recommended_mode = 'needs_configuration'
        next_steps = [
            'Configura OPENCLAW_BASE_URL en EasyPanel.',
            'Define API_CENTRAL_URL para que OpenClaw y secretaria sepan a donde llamar.',
            'Cuando el base_url exista, podras conectarlo al resto del sistema.',
        ]

    return {
        'enabled': config['enabled'],
        'base_url': config['base_url'],
        'has_api_key': config['has_api_key'],
        'api_central_url': config['api_central_url'],
        'recommended_mode': recommended_mode,
        'next_steps': next_steps,
    }
