# API CENTRAL

Base del sistema para tu stack de agente personal.

La idea de este repo es servir como punto común para:

- `Claude Code` como interfaz/agente de desarrollo
- `OpenClaw` como capa operativa opcional para mensajería y automatización
- `Ollama` como backend de modelo
- `Notion MCP` como puente hacia tu workspace de Notion
- un transcriptor aparte para tus clases de inglés
- tu VPS y EasyPanel como lugar de despliegue

## Estado actual

La v1 actual ya trae una API útil para arrancar:

- `GET /`
- `GET /health`
- `GET /test`
- `GET /models`
- `POST /chat`
- `GET /chat/history`
- `POST /memory/save`
- `GET /memory/list`
- `POST /tools/echo`
- `GET /auth/config`
- `GET /openclaw/config`
- `GET /notion/mcp/config`
- `GET /transcriber/config`
- `GET /telegram/config`
- `POST /telegram/webhook`
- `POST /telegram/channel/content`
- `GET /notion/config`
- `GET /notion/ideas`
- `POST /notion/ideas/drafts`

## Qué hace hoy

- conecta con Ollama para chat y listado de modelos
- guarda memoria simple en SQLite
- registra historial de chats
- recibe webhooks de Telegram
- corrige writings en privado con IA
- permite publicar en canal desde un admin autorizado
- genera borradores de Telegram desde ideas de Notion

## Qué papel tendrá cada pieza

- `API CENTRAL`: núcleo de integración y coordinación
- `Claude Code`: interfaz principal para desarrollo y trabajo sobre el repo
- `OpenClaw`: agente operativo opcional para canales, automatizaciones y tareas
- `Ollama`: motor local o cloud
- `Notion MCP`: acceso controlado a tu workspace de Notion
- `Transcriptor`: servicio aparte para convertir audio a texto
- `EasyPanel`: despliegue del servicio en el VPS

## Archivos importantes

- `main.py`: API principal
- `Dockerfile`: despliegue Docker
- `requirements.txt`: dependencias Python
- `env`: plantilla local de variables
- `.env.example`: plantilla limpia para copiar a `.env` o a EasyPanel

## Ejecutar en local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Swagger:

- http://localhost:8000/docs

## Variables de entorno

Variables actuales:

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT_SECONDS`
- `CENTRAL_DB_PATH`
- `API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_ALLOWED_ADMIN_IDS`
- `TELEGRAM_CHANNEL_ID`
- `CORRECTOR_MODEL`
- `NOTION_API_TOKEN`
- `NOTION_CONTENT_DB_ID`
- `NOTION_VERSION`
- `OPENCLAW_BASE_URL`
- `OPENCLAW_API_KEY`
- `NOTION_MCP_URL`
- `NOTION_MCP_API_KEY`
- `TRANSCRIBER_PROVIDER`
- `TRANSCRIBER_MODEL`
- `TRANSCRIBER_API_KEY`

## Seguridad basica

Si defines `API_KEY`, las rutas de escritura y publicacion quedaran protegidas con la cabecera `X-API-Key`.

Rutas protegidas cuando exista clave:

- `POST /chat`
- `POST /memory/save`
- `POST /telegram/channel/content`
- `POST /notion/ideas/drafts`
- `POST /transcriber/transcribe`

Notas:

- `POST /telegram/webhook` sigue abierto para Telegram, pero valida su propio `TELEGRAM_WEBHOOK_SECRET`.

## Despliegue en EasyPanel

Recomendado:

- puerto interno: `8000`
- healthcheck: `GET /health`
- volumen persistente para `central.db`
- variables de entorno definidas en EasyPanel
- `OLLAMA_BASE_URL` apuntando a tu instancia de Ollama

## Cómo encaja OpenClaw

La intención del proyecto es que `OpenClaw` no compita con `Claude Code` ni con esta API, sino que encaje como una capa operativa opcional:

- si quieres Telegram o automatizaciones, `OpenClaw` puede actuar encima de esta base
- si quieres solo desarrollo y control del repo, `Claude Code` sigue siendo la interfaz principal
- si quieres un sistema más limpio, mantenemos esta API como hub y vamos añadiendo conectores por fases

## Siguientes pasos recomendados

1. sube este repo a GitHub como fuente de verdad
2. configura `env` o `.env` con tus credenciales
3. despliega la API en EasyPanel
4. añade el conector de Notion MCP
5. decide si `OpenClaw` entra como agente operativo en una segunda fase
6. añade el transcriptor de clases como servicio separado
