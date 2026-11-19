# CLAUDE.md — disputes-ai-copilot

Servicio FastAPI de **disputas de transacciones** con un copiloto de IA (extracción estructurada, RAG con citas, agente, MCP, evals). Proyecto personal de portafolio, repo público, datos 100 % sintéticos. Es la mitad "IA" de un sistema de dos partes: **Bank** (otro repo, .NET, eventos) es el sistema que se opera; Disputes es el copiloto que ayuda a operarlo. Este servicio **nunca** modifica Bank.

Arquitectura y decisiones de diseño: `docs/ARCHITECTURE.md`. Principios: `.specify/memory/constitution.md`. Specs por feature: `specs/`.

## Cómo trabajar aquí
- Rol: **maestro**. El dueño intenta primero; tú explicas, planteas la tarea y revisas. Puedes generar código repetitivo (configuración, plantillas, Dockerfiles); el dueño escribe lo central (modelos, endpoints, reglas de estado) y debe poder explicarlo línea por línea antes de cada commit.
- Al empezar una sesión: lee "Estado actual" y pregunta cuál es el entregable de hoy. Un tema y un entregable por sesión; lo que aparezca fuera del plan va al parqueadero, no se abre.
- Corrige con honestidad (conceptos cruzados, razones equivocadas), sin suavizar.
- Verifica lo técnico en la documentación oficial y marca lo que no verificaste. No inventes APIs ni cifras.
- Idioma: español para conversar; código, specs, README y documentación del repo en inglés (este archivo es la excepción: es contexto de trabajo).

## Estado actual (actualizar al cerrar cada feature)
- **Hecho:** feature 001 (crear y consultar disputas), fusionada a `develop` (PR #1). Feature 002 (transiciones de estado), fusionada (PR #3), CI verde. Dockerfile e imagen en CI, fusionados (PR #4): el CI construye la imagen y prueba `/health`.
- **Hecho:** feature 003 (`LLMClient`: interfaz, doble de prueba y adaptador Anthropic), fusionada (PR #6); una llamada real manual documentada en `docs/evidence/llm-client-anthropic.md`. El adaptador de Azure OpenAI se hizo después (ver abajo).
- **Hecho:** adaptador Azure OpenAI para el mismo `LLMClient` (spec `specs/004-azure-openai-adapter`, rama `feat/004-azure-openai-adapter`); una llamada real manual documentada en `docs/evidence/llm-client-azure-openai.md`. Fusionada a `develop` (PR #8).
- **Siguiente:** `POST /disputes/intake`; su directorio de Spec Kit será `005-...` (el 004 lo tomó el adaptador Azure); rama de spec aún sin crear.
- **Pendiente sin resolver:** dos cuelgues intermitentes en `test_a_closed_dispute_is_never_changed_by_simultaneous_requests` (causa no encontrada; mitigado con un timeout de 20 s en el helper `race`). Está declarado en el PR #3.
- **Límites conocidos:** repositorio en memoria (se pierde al reiniciar; con varios workers cada proceso tiene su propia memoria); la atomicidad de las transiciones (un candado dentro del repositorio) solo vale dentro de un proceso; sin autenticación; el `LLMClient` (con dos adaptadores) existe pero ningún endpoint lo usa (la API no tiene comportamiento de IA todavía); sin reintentos ante fallos del modelo (solo la marca `retryable`); el timeout por defecto (60 s) no está validado por una medición.

## Roadmap (numeración tentativa; Spec Kit asigna la real)
| # | Feature | Estado |
|---|---|---|
| 001 | Crear y consultar disputas | Hecha |
| 002 | Transiciones de estado + concurrencia | Hecha |
| — | Dockerfile + imagen en CI (infraestructura) | Hecha (PR #4) |
| 003 | `LLMClient`: interfaz, doble de prueba, adaptador Anthropic | Hecha (PR #6) |
| — | Adaptador Azure OpenAI para el mismo `LLMClient` (spec `004-azure-openai-adapter`) | Hecha (PR #8) |
| 004 | `POST /disputes/intake`: texto libre a disputa validada (salida estructurada); su spec será `005-...` | Pendiente |
| 005 | Evals: dataset de 30 casos y script (aciertos, latencia, costo) | Pendiente |
| 006 | Persistencia en PostgreSQL con Alembic | Pendiente |
| 007 | RAG con citas sobre políticas y docs de Bank (pgvector) | Pendiente |
| 008 | Despliegue público v0 (Azure Container Apps, escala a cero, tope diario de llamadas) | Pendiente |
| 009 | Agente LangGraph con herramientas `get_dispute` y `search_policy` | Pendiente |
| 010 | Servidor MCP de solo lectura (disputas y estado de transferencias de Bank) + CI/CD de despliegue | Pendiente |
| 011 | Caché Redis (ahorro medido) y Langfuse con prompts versionados | Pendiente |
| 012 | Guardrails (PII, inyección de prompts) y evals v2 con 2 o 3 modelos | Pendiente |

## Decisiones ya tomadas
- `DisputeCreate` (entrada) separado de `Dispute` (registro); la entrada usa `extra="forbid"`.
- Repositorio detrás de un `Protocol`; se reemplaza por PostgreSQL sin tocar las rutas.
- Un solo formato de error para todos los errores, incluidos los del framework.
- Imagen Docker en dos etapas, usuario no root y **un solo** proceso uvicorn (el almacén en memoria y su candado son por proceso). El CI la construye y prueba `/health`; no se publica en ningún registro hasta la feature 008.
- Búsqueda vectorial con `pgvector` dentro de PostgreSQL, no una base vectorial aparte.
- El agente se construye una sola vez, en LangGraph. Las pruebas unitarias nunca llaman a un modelo real: usan un doble de `LLMClient`.
- `LLMClient` es un `Protocol` async con `complete(LLMRequest) -> LLMResponse`. Los tipos son Pydantic inmutables, sin parámetros de muestreo (`temperature`, `top_p`, `top_k`: se rechazan). La respuesta lleva texto, uso de tokens, el modelo que respondió y un motivo de parada neutral (`completed`, `max_tokens`, `other`); una respuesta cortada por el límite de tokens se devuelve, no se lanza. No valida el orden de los turnos (lo rechaza el proveedor).
- Fallos del modelo: `LLMError` y cinco subclases (autenticación, petición inválida, límite de tasa, timeout, proveedor no disponible), cada una con `retryable` como atributo de clase. `LLMConfigurationError` no hereda de `LLMError`. Los reintentos serán una feature deliberada que lea `retryable`.
- El adaptador de Anthropic hace **un solo intento** por llamada (`max_retries=0` en el SDK). Traduce por clase de excepción del SDK; el mensaje es propio (nunca `str()` del error del proveedor) y se lanza fuera del bloque `except`, para que ni `__cause__` ni `__context__` guarden la petición con la clave.
- Settings del LLM: `ANTHROPIC_API_KEY` (`SecretStr`), `LLM_MODEL` (obligatorio, sin valor por defecto) y `LLM_TIMEOUT_SECONDS` (por defecto 60; es la espera máxima por fase, no un tope total). Se leen al construir el adaptador, no al importar el módulo.
- `FakeLLMClient` vive en `tests/`, no en el paquete. `tests/conftest.py` hace fallar cualquier prueba que intente una conexión de red a un host que no sea local.
- Adaptador Azure OpenAI: `openai.AsyncOpenAI` apuntando al endpoint v1 de Azure (no `AzureOpenAI`), `max_retries=0`. Envía `max_completion_tokens` (el servicio rechaza `max_tokens`), el nombre del despliegue como `model` y el system prompt como mensaje `system` (aceptado por el despliegue probado). `finish_reason`: `stop` a `completed`, `length` a `max_tokens`, el resto a `other`. Variables: `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY` (`SecretStr`), `AZURE_OPENAI_DEPLOYMENT`, más el `LLM_TIMEOUT_SECONDS` compartido; `LLM_MODEL` no se usa. Una respuesta sin texto o sin `usage` lanza `LLMError` base (no reintentable); el adaptador de Anthropic devuelve texto vacío en ese caso (las pruebas de 003 no se tocan): inconsistencia conocida. El timeout 408 llega como `APIStatusError` genérico y se traduce por código de estado.
- Pruebas compartidas: `tests/test_llm_contract.py` + `tests/llm_harness.py` corren las mismas comprobaciones contra el fake y ambos adaptadores.
- Bank es solo lectura y con datos de ejemplo; la interacción pasa por una interfaz documentada.
- Estados: `open`, `under_review`, `resolved`, `rejected`, `withdrawn`. Cinco transiciones permitidas: `open → under_review`, `open → withdrawn`, `under_review → resolved`, `under_review → rejected`, `under_review → withdrawn`. `under_review → withdrawn` sí; `open → rejected` no. Los estados finales nunca se reabren y pasar al estado actual se rechaza. Las reglas viven en una sola tabla (`transitions.py`).
- `POST /disputes/{id}/transitions` con `{to_state, note}`; una transición inválida devuelve 409 con código `invalid_transition` y el formato de error de la API.
- Concurrencia: transición condicional atómica en el repositorio ("cambia a X solo si el estado actual es Y"), con un candado en memoria; con PostgreSQL será un `UPDATE ... WHERE state = ...`. Si falla, se responde 409 sin reintentar.
- Motivo `devolution` renombrado a `refund_not_received`, sin alias para el valor viejo. `updated_at` en cada disputa y un historial de cambios (`history`) incrustado en la disputa.

## Stack y comandos
Python 3.12, FastAPI, Pydantic v2, uv, ruff, pytest, Docker Compose. PostgreSQL con SQLAlchemy async y Alembic llega en la feature 006.
- Instalar: `uv sync`
- Servidor: `uv run uvicorn disputes.main:app --reload`
- Pruebas: `uv run pytest`
- Lint: `uv run ruff check .`
- Postgres local: `docker compose up -d postgres`

## Reglas del repo
- Ramas de feature con PR hacia `develop`; `main` solo recibe merges de `develop`. El CI debe estar verde antes de fusionar.
- Pruebas primero (rojo, luego verde), pero pocas y centradas en lo fundamental (constitución v2.0.0, Principio I): reglas de negocio, concurrencia y seguridad. Sin número fijo por feature; si el plan prevé más de ~15 pruebas, justificarlo en una línea. No probar lo que el framework ya garantiza; los casos borde de bajo riesgo van a una lista. Cada prueba debe poder explicarse línea por línea. Las pruebas de las features 001-003 no se tocan.
- Cada feature sigue Spec Kit: spec, clarify, plan, tasks, analyze, implementación.
- El README y la documentación afirman solo lo que existe y está probado; lo planeado se etiqueta como planeado. Cifras medidas, nunca inventadas.
- Nunca versionar claves ni datos reales. Las claves se leen del entorno; los archivos de ejemplo llevan marcadores.
- Una dependencia central nueva requiere justificación en el plan de la feature o una enmienda de la constitución.
- El plan personal de estudio y búsqueda de empleo es privado y **no** se copia a este repo. Si existe `CLAUDE.local.md` (no versionado), léelo.

## Al cerrar una feature
1. Actualizar "Estado actual" y la tabla del roadmap en este archivo.
2. Actualizar la sección Roadmap del `README.md` y, si cambió el diseño, `docs/ARCHITECTURE.md`.
3. Mover a "Decisiones ya tomadas" lo que se haya confirmado.
4. PR hacia `develop` con el CI en verde.
