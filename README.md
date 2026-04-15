# API CENTRAL

Base del sistema para tu stack de agente personal.

Este repo existe para ser el punto comun entre:

- `Claude Code` como interfaz/agente de desarrollo
- `OpenClaw` como capa operativa opcional
- `Ollama` como backend de modelo
- `Notion MCP` como puente hacia tu workspace de Notion
- un transcriptor en vivo para tus clases de ingles
- tu VPS y EasyPanel como lugar de despliegue

## Estado actual verificado

La API ya esta desplegada y funcionando en EasyPanel.

URLs verificadas:

- `GET /health`: `https://central-api.vdwbjc.easypanel.host/health`
- `GET /models`: `https://central-api.vdwbjc.easypanel.host/models`
- `POST /chat`: `https://central-api.vdwbjc.easypanel.host/chat`
- `GET /openclaw/plan`: `https://central-api.vdwbjc.easypanel.host/openclaw/plan`
- `GET /transcriber/plan`: `https://central-api.vdwbjc.easypanel.host/transcriber/plan`

Estado comprobado en produccion:

- `API CENTRAL` responde `200` en `/health`
- `Ollama` esta conectado por URL interna
- modelo por defecto actual: `llama3.2:latest`
- OpenClaw todavia no esta configurado, pero ya hay endpoint de plan
- el transcriptor ya esta preparado para modo `live`

## Arquitectura que estamos siguiendo

- `API CENTRAL`: nucleo de integracion y coordinacion
- `Claude Code`: interfaz principal para desarrollo y trabajo sobre el repo
- `OpenClaw`: agente operativo opcional para canales, automatizaciones y tareas
- `Ollama`: motor local o cloud
- `Notion MCP`: acceso controlado a tu workspace de Notion
- `Transcriber`: servicio aparte para audio en vivo
- `EasyPanel`: despliegue del servicio en el VPS

## Lo que hace hoy la API

- conecta con Ollama para chat y listado de modelos
- guarda memoria simple en SQLite
- registra historial de chats
- recibe webhooks de Telegram
- corrige writings en privado con IA
- permite publicar en canal desde un admin autorizado
- genera borradores de Telegram desde ideas de Notion
- expone un plan de configuracion para OpenClaw
- expone un plan de configuracion para transcripcion en vivo
- mantiene sesiones de transcripcion live con start/chunk/stop

## Endpoints importantes

### Sistema

- `GET /`
- `GET /health`
- `GET /test`
- `GET /models`
- `POST /chat`
- `GET /chat/history`
- `POST /memory/save`
- `GET /memory/list`
- `POST /tools/echo`

### Seguridad

- `GET /auth/config`

### OpenClaw

- `GET /openclaw/config`
- `GET /openclaw/plan`

### Notion

- `GET /notion/mcp/config`
- `GET /notion/config`
- `GET /notion/ideas`
- `POST /notion/ideas/drafts`

### Transcriber

- `GET /transcriber/config`
- `GET /transcriber/plan`
- `POST /transcriber/transcribe`
- `POST /transcriber/live/start`
- `POST /transcriber/live/{session_id}/chunk`
- `GET /transcriber/live/{session_id}`
- `POST /transcriber/live/{session_id}/stop`

### Telegram

- `GET /telegram/config`
- `POST /telegram/webhook`
- `POST /telegram/channel/content`

## Variables de entorno

Estas son las variables que usa la API:

```env
CENTRAL_DB_PATH=/app/data/central.db
API_KEY=
OLLAMA_BASE_URL=http://ollama_ollama:11434
OLLAMA_MODEL=llama3.2:latest
OLLAMA_TIMEOUT_SECONDS=60

TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_ALLOWED_ADMIN_IDS=
TELEGRAM_CHANNEL_ID=
CORRECTOR_MODEL=

NOTION_API_TOKEN=
NOTION_CONTENT_DB_ID=
NOTION_VERSION=2022-06-28

OPENCLAW_BASE_URL=
OPENCLAW_API_KEY=
NOTION_MCP_URL=
NOTION_MCP_API_KEY=

TRANSCRIBER_PROVIDER=faster-whisper
TRANSCRIBER_MODE=live
TRANSCRIBER_MODEL=small
TRANSCRIBER_API_KEY=
```

Notas rapidas:

- `API_KEY` puede ir vacia al principio
- `OLLAMA_BASE_URL` debe apuntar a la URL interna que ya validamos en EasyPanel
- `OLLAMA_MODEL` ahora mismo funciona con `llama3.2:latest`
- `TRANSCRIBER_MODE` debe quedarse en `live` para audio en directo

## Seguridad basica

Si defines `API_KEY`, las rutas de escritura y publicacion quedan protegidas con la cabecera `X-API-Key`.

Rutas protegidas cuando exista clave:

- `POST /chat`
- `POST /memory/save`
- `POST /telegram/channel/content`
- `POST /notion/ideas/drafts`
- `POST /transcriber/transcribe`
- `POST /transcriber/live/start`
- `POST /transcriber/live/{session_id}/chunk`
- `GET /transcriber/live/{session_id}`
- `POST /transcriber/live/{session_id}/stop`

Notas:

- `POST /telegram/webhook` sigue abierto para Telegram, pero valida su propio `TELEGRAM_WEBHOOK_SECRET`

## Despliegue en EasyPanel

Configuracion recomendada:

- repo: `Gavcor74/central-api`
- branch: `main`
- build path: `/`
- puerto interno: `8000`
- healthcheck: `GET /health`
- volumen persistente para `central.db`
- variables de entorno definidas en EasyPanel
- `OLLAMA_BASE_URL` apuntando a tu instancia interna de Ollama

## Handoff para el sobremesa

Si vas a seguir desde el ordenador de sobremesa, la fuente de verdad es GitHub.

### Clonar desde cero

```bash
mkdir -p ~/Escritorio/Linux_Codex
cd ~/Escritorio/Linux_Codex
git clone https://github.com/Gavcor74/central-api.git "API CENTRAL"
```

### Si la carpeta ya existe

```bash
cd ~/Escritorio/Linux_Codex/API\ CENTRAL
git pull origin main
```

### Verificacion rapida

```bash
curl -s https://central-api.vdwbjc.easypanel.host/health
curl -s https://central-api.vdwbjc.easypanel.host/openclaw/plan
curl -s https://central-api.vdwbjc.easypanel.host/transcriber/plan
```

## Flujo de transcripcion en vivo

La parte de transcripcion esta pensada para audio en directo, no para subir ficheros sueltos.

Flujo minimo:

1. crear sesion con `POST /transcriber/live/start`
2. ir mandando chunks con `POST /transcriber/live/{session_id}/chunk`
3. consultar la sesion con `GET /transcriber/live/{session_id}`
4. cerrar la sesion con `POST /transcriber/live/{session_id}/stop`

Ejemplo de inicio de sesion:

```bash
curl -s -X POST https://central-api.vdwbjc.easypanel.host/transcriber/live/start
-H 'Content-Type: application/json'
-d '{"language":"en","sample_rate":16000,"mime_type":"audio/webm","notes":"Clase de ingles en vivo"}'
```

Ejemplo de chunk de prueba:

```bash
curl -s -X POST https://central-api.vdwbjc.easypanel.host/transcriber/live/TU_SESSION_ID/chunk
-H 'Content-Type: application/json'
-d '{"chunk_kind":"text","text_chunk":"test parcial","is_final":false}'
```

Consultar sesion:

```bash
curl -s https://central-api.vdwbjc.easypanel.host/transcriber/live/TU_SESSION_ID
```

Cerrar sesion:

```bash
curl -s -X POST https://central-api.vdwbjc.easypanel.host/transcriber/live/TU_SESSION_ID/stop
```

## OpenClaw

OpenClaw todavia no esta configurado en este despliegue, pero ya tiene su sitio en la arquitectura.

Rutas actuales:

- `GET /openclaw/config`
- `GET /openclaw/plan`

Cuando quieras conectarlo de verdad, rellenas:

- `OPENCLAW_BASE_URL`
- `OPENCLAW_API_KEY`

## Siguientes pasos recomendados

1. dejar este repo como fuente de verdad en GitHub
2. seguir desde el sobremesa con `git pull`
3. implementar un cliente web minimo para audio en vivo
4. conectar de verdad el motor de transcripcion al flujo de chunks
5. decidir si OpenClaw va a vivir como gateway externo o como servicio del VPS
6. conectar Notion MCP mas adelante, cuando el agente ya este estable
