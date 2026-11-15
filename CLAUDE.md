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
- **Hecho:** feature 001 (crear y consultar disputas). Fusionada a `develop` (PR #1), CI verde.
- **Siguiente:** feature 002, transiciones de estado (ver abajo). Después, Dockerfile e imagen en CI como cambio de infraestructura aparte.
- **Límites conocidos:** repositorio en memoria (se pierde al reiniciar; con varios workers cada proceso tiene su propia memoria); único estado `open`; sin autenticación; sin componentes de IA.

### Feature 002 — transiciones de estado
- Estados: `open → under_review → resolved | rejected`, y `open → withdrawn`. Los estados finales (`resolved`, `rejected`, `withdrawn`) nunca se reabren.
- Endpoint propuesto: `POST /disputes/{id}/transitions` con `{to_state, note}`.
- Una transición inválida devuelve 409 con el mismo formato de error de la API (constitución II y IV).
- Concurrencia: si dos transiciones incompatibles llegan a la vez sobre la misma disputa, se aplica exactamente una y la otra recibe 409. La implementación debe ser una transición condicional atómica en el repositorio ("cambia a X solo si el estado actual es Y"), no una lectura seguida de una escritura. En memoria es un candado dentro del repositorio; con PostgreSQL será un `UPDATE ... WHERE state = ...`. Se prueba con peticiones en paralelo.
- Decisiones abiertas (propuestas, sin confirmar): renombrar el motivo `devolution` a `refund_not_received`; agregar `updated_at`; guardar un historial de cambios de estado.

## Roadmap (numeración tentativa; Spec Kit asigna la real)
| # | Feature | Estado |
|---|---|---|
| 001 | Crear y consultar disputas | Hecha |
| 002 | Transiciones de estado + concurrencia | Siguiente |
| — | Dockerfile + imagen en CI (infraestructura) | Pendiente |
| 003 | `LLMClient`: interfaz, doble de prueba, adaptador Anthropic, adaptador Azure OpenAI | Pendiente |
| 004 | `POST /disputes/intake`: texto libre a disputa validada (salida estructurada) | Pendiente |
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
- Búsqueda vectorial con `pgvector` dentro de PostgreSQL, no una base vectorial aparte.
- El agente se construye una sola vez, en LangGraph. Las pruebas unitarias nunca llaman a un modelo real: usan un doble de `LLMClient`.
- Bank es solo lectura y con datos de ejemplo; la interacción pasa por una interfaz documentada.

## Stack y comandos
Python 3.12, FastAPI, Pydantic v2, uv, ruff, pytest, Docker Compose. PostgreSQL con SQLAlchemy async y Alembic llega en la feature 006.
- Instalar: `uv sync`
- Servidor: `uv run uvicorn disputes.main:app --reload`
- Pruebas: `uv run pytest`
- Lint: `uv run ruff check .`
- Postgres local: `docker compose up -d postgres`

## Reglas del repo
- Ramas de feature con PR hacia `develop`; `main` solo recibe merges de `develop`. El CI debe estar verde antes de fusionar.
- Pruebas primero (rojo, luego verde). Cada feature sigue Spec Kit: spec, clarify, plan, tasks, analyze, implementación.
- El README y la documentación afirman solo lo que existe y está probado; lo planeado se etiqueta como planeado. Cifras medidas, nunca inventadas.
- Nunca versionar claves ni datos reales. Las claves se leen del entorno; los archivos de ejemplo llevan marcadores.
- Una dependencia central nueva requiere justificación en el plan de la feature o una enmienda de la constitución.
- El plan personal de estudio y búsqueda de empleo es privado y **no** se copia a este repo. Si existe `CLAUDE.local.md` (no versionado), léelo.

## Al cerrar una feature
1. Actualizar "Estado actual" y la tabla del roadmap en este archivo.
2. Actualizar la sección Roadmap del `README.md` y, si cambió el diseño, `docs/ARCHITECTURE.md`.
3. Mover a "Decisiones ya tomadas" lo que se haya confirmado.
4. PR hacia `develop` con el CI en verde.
