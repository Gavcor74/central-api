# Handoff

## Objetivo del proyecto

`API CENTRAL` es la base común para tu stack de agente personal:

- `Claude Code` como interfaz de desarrollo
- `OpenClaw` como capa operativa opcional
- `Ollama` como backend de modelo
- `Notion MCP` como puente hacia Notion
- un transcriptor aparte para clases de inglés
- despliegue en tu VPS / EasyPanel

## Flujo objetivo

Para tareas delicadas, el orden recomendado es:

1. `secretaria` recibe el mensaje por Telegram.
2. `secretaria` llama a `API CENTRAL`.
3. `API CENTRAL` interpreta, prepara el borrador y decide si hace falta confirmación.
4. `OpenClaw` ejecuta solo cuando la acción ya está aprobada.
5. `API CENTRAL` registra todo y devuelve el resultado.

Regla práctica:

- `API CENTRAL` decide
- `OpenClaw` ejecuta
- `secretaria` habla con el usuario
- `Ollama` redacta y ayuda a razonar

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

- conectar `secretaria` a `API CENTRAL` como entrada principal
- integrar `OpenClaw` como capa de ejecución cuando haya aprobación
- conector de Notion MCP si queremos acceso más directo al workspace
- transcriptor de audio a texto
- separación en módulos si el proyecto crece

## Variables nuevas recomendadas

En EasyPanel, para que el flujo quede claro, define también:

- `API_CENTRAL_URL=http://api:8000`
- `OPENCLAW_BASE_URL=...`
- `OPENCLAW_API_KEY=...`

Y en `secretaria`, haz que el bot apunte a `API CENTRAL` en vez de hablar con Ollama directamente para tareas operativas.

## OpenClaw en EasyPanel

Si `openclaw` se queda con `exit code: 0`, no lo trates como un bot vivo todavía.

Revisa que el servicio use:

- un proceso persistente de Gateway
- `gateway.bind=lan` cuando publique puerto
- persistencia para `/home/node/.openclaw`
- auth por token o password
- `--allow-unconfigured` solo para el primer bootstrap si la config no existe todavía

Comando de referencia:

```bash
openclaw gateway --port 18789 --bind lan --allow-unconfigured
```

Variables mínimas de referencia:

- `OPENCLAW_GATEWAY_PORT=18789`
- `OPENCLAW_GATEWAY_BIND=lan`
- `OPENCLAW_GATEWAY_TOKEN=...`
- `OPENCLAW_STATE_DIR=/home/node/.openclaw`
- `OPENCLAW_CONFIG_PATH=/home/node/.openclaw/openclaw.json`
- `API_CENTRAL_URL=http://api:8000`

## Regla de trabajo

GitHub es la fuente de verdad. Todo cambio importante debe quedar subido para poder continuar desde cualquier ordenador.
