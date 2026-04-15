# Handoff

## Objetivo del proyecto

`API CENTRAL` es la base común para tu stack de agente personal:

- `Claude Code` como interfaz de desarrollo
- `OpenClaw` como capa operativa opcional
- `Ollama` como backend de modelo
- `Notion MCP` como puente hacia Notion
- un transcriptor aparte para clases de inglés
- despliegue en tu VPS / EasyPanel

## Estado actual

La API ya incluye:

- salud del servicio
- chat contra Ollama
- memoria simple en SQLite
- historial de chats
- Telegram webhook
- publicación en canal
- borradores desde Notion

## Archivos clave

- `main.py`: API principal
- `Dockerfile`: despliegue Docker
- `requirements.txt`: dependencias
- `env`: plantilla local de variables
- `.env.example`: plantilla para copiar a EasyPanel

## Qué falta por construir

- integración real con OpenClaw si decidimos activarla
- conector de Notion MCP si queremos acceso más directo al workspace
- transcriptor de audio a texto
- separación en módulos si el proyecto crece

## Regla de trabajo

GitHub es la fuente de verdad. Todo cambio importante debe quedar subido para poder continuar desde cualquier ordenador.
