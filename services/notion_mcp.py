from __future__ import annotations

import os


def get_notion_mcp_config() -> dict[str, object]:
    url = os.getenv('NOTION_MCP_URL', '').strip()
    api_key = os.getenv('NOTION_MCP_API_KEY', '').strip()
    return {
        'enabled': bool(url),
        'url': url or None,
        'has_api_key': bool(api_key),
    }
