# HANDOFF API CENTRAL

## Fuente de verdad

- repo oficial: `Gavcor74/central-api`
- trabajar solo sobre lo que exista en el repo oficial
- no mezclar backups locales ni archivos fuera de GitHub con esta base

## Estado operativo actual

- `API CENTRAL` es el hub del sistema
- esta pensado para vivir en el `VPS`
- `Telegram` es el canal principal
- `Ollama` es el motor de respuesta
- `OpenClaw` queda en el sobremesa como capa experimental y opcional

## Regla de arquitectura

- `VPS` = estable y publico
- `Sobremesa` = experimental y local

## Flujo principal

- `Telegram -> API CENTRAL -> Ollama`

## Flujo opcional

- `API CENTRAL -> OpenClaw` si OpenClaw esta disponible

## Decision importante sobre OpenClaw

- no es nucleo de produccion por ahora
- produccion no debe depender de el
- no moverlo al VPS por obligacion
- no borrarlo del sobremesa mientras siga aportando valor para pruebas

## Lo que ya funciona

- `GET /health`
- `GET /models`
- `POST /chat`
- `POST /telegram/webhook`
- `GET /telegram/config`
- `POST /telegram/channel/content`
- `GET /notion/config`
- `GET /notion/ideas`
- `POST /notion/ideas/drafts`
- `GET /openclaw/config`
- `GET /openclaw/health`
- `POST /openclaw/plan`

## Regla sobre Telegram

- no tocar el flujo actual de Telegram del repo oficial salvo que sea estrictamente necesario
- cualquier integracion de `OpenClaw` debe ir en paralelo y aislada

## Siguientes frentes utiles

1. mini interfaz web tipo ChatGPT conectada a `API CENTRAL`
2. captura real de audio desde navegador para la transcripcion live
3. integracion opcional real con `OpenClaw` sin volverlo dependencia critica
4. evolucion de Notion como fuente editorial
