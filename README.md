# API CENTRAL

Base inicial de una central propia desplegable en Easy Panel.

Esta v1 convierte el proyecto en una API util y reutilizable desde otros hilos o sesiones:

- expone endpoints de salud del servicio
- conecta con Ollama para chat y listado de modelos
- guarda memoria simple en SQLite
- registra historial de chats
- recibe webhooks de Telegram
- corrige writings en privado con IA
- permite publicar en canal desde un admin autorizado
- deja una base clara para integrar Telegram, WhatsApp, OpenClaw o un panel propio

## Estado actual

La API ya incluye:

- `GET /`
- `GET /health`
- `GET /test`
- `GET /models`
- `POST /chat`
- `GET /chat/history`
- `POST /memory/save`
- `GET /memory/list`
- `POST /tools/echo`
- `GET /telegram/config`
- `POST /telegram/webhook`
- `POST /telegram/channel/content`
- `GET /notion/config`
- `GET /notion/ideas`
- `POST /notion/ideas/drafts`

Ademas, para modo local:

- `telegram_local_bot.py`
  - ejecuta el bot por long polling desde tu PC

## Variables de entorno

- `OLLAMA_BASE_URL`
  - URL base de Ollama
  - valor por defecto: `http://localhost:11434`
- `OLLAMA_MODEL`
  - modelo por defecto para `POST /chat`
  - si no se define, la API intenta usar el primer modelo disponible en Ollama
- `OLLAMA_TIMEOUT_SECONDS`
  - timeout para llamadas a Ollama
  - valor por defecto: `60`
- `CENTRAL_DB_PATH`
  - ruta del archivo SQLite
  - valor por defecto: `./central.db`
- `TELEGRAM_BOT_TOKEN`
  - token del bot de Telegram
- `TELEGRAM_WEBHOOK_SECRET`
  - secret token del webhook para validar peticiones de Telegram
- `TELEGRAM_ALLOWED_ADMIN_IDS`
  - lista separada por comas con IDs de usuarios admin
- `TELEGRAM_CHANNEL_ID`
  - id del canal donde el admin puede publicar usando `/publish`
- `CORRECTOR_MODEL`
  - modelo opcional para corregir writings
  - si no se define, usa `OLLAMA_MODEL`
- `NOTION_API_TOKEN`
  - token de la integracion interna de Notion usada solo para la DB editorial
- `NOTION_CONTENT_DB_ID`
  - id de la base de datos editorial de Notion
- `NOTION_VERSION`
  - version de la API de Notion
  - valor por defecto: `2022-06-28`

Puedes crear un archivo `.env` a partir de [/.env.example](C:\Users\Jesus\OneDrive\Escritorio HP Casa\API CENTRAL\.env.example).

## Ejecutar en local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Swagger:

- [http://localhost:8000/docs](http://localhost:8000/docs)

## Probar endpoints

Salud del servicio:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Listado de modelos:

```powershell
Invoke-RestMethod http://localhost:8000/models
```

Chat con Ollama:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/chat `
  -ContentType "application/json" `
  -Body '{"message":"Hola, quien eres?"}'
```

Guardar memoria:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/memory/save `
  -ContentType "application/json" `
  -Body '{"content":"Recordar revisar el VPS","source":"manual"}'
```

Ver memoria:

```powershell
Invoke-RestMethod http://localhost:8000/memory/list
```

Ideas pendientes desde Notion:

```powershell
Invoke-RestMethod http://localhost:8000/notion/ideas
```

Generar borradores desde ideas de Notion:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/notion/ideas/drafts `
  -ContentType "application/json" `
  -Body '{"limit":3,"status":"Idea"}'
```

Generar contenido para el canal de Telegram:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/telegram/channel/content `
  -ContentType "application/json" `
  -Body '{"topic":"difference between say and tell","angle":"explica la diferencia con ejemplos faciles","include_cta":false,"publish":false}'
```

Generar y publicar directamente en el canal:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/telegram/channel/content `
  -ContentType "application/json" `
  -Body '{"topic":"3 ways to sound more natural in english","objective":"crear un post corto y muy publicable","publish":true}'
```

## Despliegue en Easy Panel

La imagen actual del proyecto es valida para un servicio Docker sencillo.

Config recomendada:

- puerto interno: `8000`
- healthcheck: `GET /health`
- volumen persistente opcional para conservar `central.db`
- variable `OLLAMA_BASE_URL` apuntando a tu instancia de Ollama
- variables de Telegram configuradas en Easy Panel

Ejemplo si Ollama vive en otra maquina o servicio:

- `OLLAMA_BASE_URL=http://IP_O_HOST:11434`

## Arquitectura de esta v1

- `FastAPI` como capa HTTP
- `Ollama` como backend de modelos
- `SQLite` como memoria inicial
- `Telegram Webhook` como primer canal real
- `Dockerfile` listo para despliegue

## AGENTE 2026 Telegram v1

Esta version ya contempla un primer caso de uso real:

- un usuario escribe por privado al bot
- envia un writing en ingles
- la API lo corrige con IA
- el bot devuelve feedback estructurado

Tambien incluye una accion simple para admins:

- un admin autorizado puede enviar `/publish texto`
- la API publica ese contenido en el canal configurado

Ahora tambien incluye una via directa por API:

- generar borradores para el canal con `POST /telegram/channel/content`
- publicarlos en el canal con `publish=true`

## Modo Local Recomendado

Si quieres que todo funcione desde tu PC mientras trabajas, esta es la opcion mas simple:

- `Ollama` en tu PC
- `telegram_local_bot.py` en tu PC
- `SQLite` local como memoria
- `OpenClaw` opcional para explorar otras tareas

En este modo no hace falta webhook publico ni VPS para empezar.

### Arranque local del bot

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python telegram_local_bot.py
```

El bot quedara activo mientras tu PC este encendido y el proceso siga corriendo.

Tambien puedes arrancarlo con el script:

```powershell
.\start_local_agent.ps1
```

### Flujo privado

- `private chat`
- texto libre
- correccion con modelo de Ollama
- respuesta con:
  - nivel estimado
  - errores principales
  - texto corregido
  - consejos breves

### Flujo canal

- el bot puede publicar en canal usando `/publish`
- pensado para que el admin lo use desde privado

## Configuracion de Telegram

1. Crea el bot con BotFather
2. Guarda el token en `TELEGRAM_BOT_TOKEN`
3. Configura `TELEGRAM_WEBHOOK_SECRET`
4. Añade tu ID en `TELEGRAM_ALLOWED_ADMIN_IDS`
5. Configura `TELEGRAM_CHANNEL_ID`
6. Registra el webhook contra:

```text
https://TU_DOMINIO/telegram/webhook
```

Ejemplo con Telegram:

```text
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://TU_DOMINIO/telegram/webhook&secret_token=TU_SECRET
```

## Estrategia recomendada ahora

Para esta fase del proyecto:

1. probar y validar el bot en local con `telegram_local_bot.py`
2. usar el VPS solo mas adelante si el flujo demuestra valor real
3. dejar RAG/memoria avanzada para una siguiente iteracion

## Fases del proyecto

### Fase 1: v1 local

Objetivo:

- bot de Telegram en local
- writings por privado
- `/publish` para admin
- Ollama local como motor
- memoria tecnica base en `OpenClaw`

### Fase 2: supervision editorial

Objetivo:

- introducir `NocoDB`
- guardar borradores y publicaciones del canal
- revisar, aprobar y evitar repeticiones

### Fase 3: despliegue remoto si compensa

Objetivo:

- mover partes al VPS o a otro servidor solo cuando el flujo ya este validado

## Arquitectura objetivo: OpenClaw como nucleo

La vision actual del proyecto queda asi:

- `OpenClaw` = nucleo del agente
- `Telegram` = canal de entrada y salida
- `Ollama` = motor de lenguaje local
- memoria interna nativa de `OpenClaw` = memoria tecnica interna
- `NocoDB` = supervision editorial del contenido del canal
- `n8n` = capa de automatizacion y ejecucion de flujos

### Reparto de papeles

#### OpenClaw

Papel:

- cerebro del agente
- orquestacion de herramientas
- contexto conversacional
- agente principal sobre tu PC

#### Telegram

Papel:

- canal publico y privado
- interaccion con alumnos o usuarios
- envio de writings
- publicacion y gestion del canal

#### Ollama

Papel:

- inferencia local
- correccion de writings
- generacion de contenido
- razonamiento base del agente

#### SQLite

Papel:

- opcion tecnica futura si alguna parte propia necesita persistencia separada
- no es la memoria tecnica principal mientras `OpenClaw` ya cubra esa capa

#### NocoDB

Papel:

- supervision humana del contenido
- revision de borradores
- control de publicaciones
- deteccion editorial de repeticion

#### n8n

Papel:

- automatizaciones
- workflows
- ejecucion de integraciones
- soporte operativo del agente

## Vision funcional de AGENTE 2026 Telegram

El sistema deberia permitir:

1. que un alumno escriba al bot por privado
2. que el agente corrija su writing
3. que tu puedas pedir al agente contenido para el canal
4. que ese contenido quede guardado para supervision
5. que el agente use memoria interna para no perder contexto
6. que mas adelante el agente pueda preparar workflows en `n8n`

## Notion como fuente editorial

La estrategia actual usa `Notion` como fuente de ideas y deja `OpenClaw` como nucleo del agente.

Flujo recomendado:

1. guardas ideas en la base editorial de Notion
2. esta API local lee solo esa DB con `NOTION_API_TOKEN` + `NOTION_CONTENT_DB_ID`
3. la API convierte las ideas pendientes en borradores estilo Quickinglés usando Ollama
4. `OpenClaw` o Telegram consumen esos borradores sin necesitar acceso directo a todo tu workspace

Esto mantiene el acceso bien acotado y evita depender de una integracion opaca dentro de OpenClaw.

### Esquema esperado de la DB

La lectura actual asume estas propiedades de Notion:

- `Idea`
- `Descripcion` o `Descripción`
- `Tipo`
- `Estado`
- `Prioridad`
- `Canal`
- `Notas`
- `Fecha`

## Importante

Aunque exista logica propia en este repositorio, la vision actual no es competir con `OpenClaw`, sino apoyarse en el como nucleo del agente y construir alrededor:

- Telegram como canal
- memoria nativa de `OpenClaw` como base tecnica
- NocoDB como supervision
- n8n como automatizacion

## Memoria y supervision

Para `AGENTE 2026 Telegram`, conviene separar dos capas:

### 1. Memoria interna del agente

Pensada para operativa tecnica y contexto del sistema.

Ubicacion recomendada:

- memoria interna nativa de `OpenClaw`

Que guardaria aqui:

- logs de Telegram
- historial tecnico
- memoria operativa
- decisiones internas
- contexto de ejecucion
- registros de entradas y salidas del bot

Ventajas:

- muy ligero
- rapido
- local
- ya existe dentro de `OpenClaw`
- evita duplicar memoria tecnica sin necesidad

### 2. Supervision editorial del contenido

Pensada para revisar y controlar lo que el agente crea para Telegram.

Ubicacion recomendada:

- `NocoDB` si mas adelante quieres interfaz visual

Que guardaria aqui:

- ideas de contenido
- borradores
- publicaciones realizadas
- estado del contenido (`draft`, `approved`, `published`, `rejected`)
- tags
- notas editoriales
- fecha de publicacion
- referencias a contenido parecido o repetido

Ventajas:

- vista tipo tabla
- edicion manual sencilla
- supervision humana mas comoda
- mejor para aprobar contenido antes de publicarlo

### Decision actual

La recomendacion actual es:

- usar primero la memoria tecnica nativa de `OpenClaw`
- valorar `NocoDB` despues como capa de supervision editorial

Asi no se mezcla la memoria tecnica del agente con el control humano del contenido.

## Siguiente fase recomendada

1. Añadir autenticacion basica por API key
2. Separar la app en carpetas (`app/routers`, `app/services`, `app/db`)
3. Integrar Telegram como primer canal
4. Añadir herramientas reales de la central
5. Conectar OpenClaw como interfaz conversacional opcional

## Documentacion de continuidad

Para retomar el proyecto desde otro hilo, revisar primero:

- [README.md](C:\Users\Jesus\OneDrive\Escritorio HP Casa\API CENTRAL\README.md)
- [docs/HANDOFF.md](C:\Users\Jesus\OneDrive\Escritorio HP Casa\API CENTRAL\docs\HANDOFF.md)
