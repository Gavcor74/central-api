from __future__ import annotations

import os


def get_openclaw_config() -> dict[str, object]:
    base_url = os.getenv('OPENCLAW_BASE_URL', '').strip()
    api_key = os.getenv('OPENCLAW_API_KEY', '').strip()
    api_central_url = os.getenv('API_CENTRAL_URL', '').strip()
    gateway_port = os.getenv('OPENCLAW_GATEWAY_PORT', '18789').strip()
    gateway_bind = os.getenv('OPENCLAW_GATEWAY_BIND', 'lan').strip()
    gateway_token = os.getenv('OPENCLAW_GATEWAY_TOKEN', '').strip()
    state_dir = os.getenv('OPENCLAW_STATE_DIR', '').strip()
    config_path = os.getenv('OPENCLAW_CONFIG_PATH', '').strip()
    return {
        'enabled': bool(base_url),
        'base_url': base_url or None,
        'has_api_key': bool(api_key),
        'api_central_url': api_central_url or None,
        'gateway_port': int(gateway_port) if gateway_port.isdigit() else None,
        'gateway_bind': gateway_bind or None,
        'has_gateway_token': bool(gateway_token),
        'state_dir': state_dir or None,
        'config_path': config_path or None,
    }


def get_openclaw_plan() -> dict[str, object]:
    config = get_openclaw_config()
    if config['enabled']:
        recommended_mode = 'vps_gateway'
        next_steps = [
            'Conecta OpenClaw a API CENTRAL como cerebro de decisión.',
            'Mantén Ollama en la URL interna que ya validaste.',
            'Usa OpenClaw solo para ejecutar acciones aprobadas.',
            'Asegura un proceso largo de Gateway y persistencia para ~/.openclaw.',
        ]
    else:
        recommended_mode = 'needs_configuration'
        next_steps = [
            'Configura OPENCLAW_BASE_URL en EasyPanel.',
            'Define API_CENTRAL_URL para que OpenClaw y secretaria sepan a donde llamar.',
            'Define OPENCLAW_GATEWAY_TOKEN, OPENCLAW_GATEWAY_BIND y persistencia de estado.',
            'Cuando el base_url exista, podras conectarlo al resto del sistema.',
        ]

    return {
        'enabled': config['enabled'],
        'base_url': config['base_url'],
        'has_api_key': config['has_api_key'],
        'api_central_url': config['api_central_url'],
        'gateway_port': config['gateway_port'],
        'gateway_bind': config['gateway_bind'],
        'has_gateway_token': config['has_gateway_token'],
        'state_dir': config['state_dir'],
        'config_path': config['config_path'],
        'recommended_mode': recommended_mode,
        'next_steps': next_steps,
    }
