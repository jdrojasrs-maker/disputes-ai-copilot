# Disputes AI Copilot

![CI](https://github.com/jdrojasrs-maker/disputes-ai-copilot/actions/workflows/ci.yml/badge.svg)

Servicio **FastAPI** para gestionar disputas de transacciones (un cliente reclama un cobro), con un copiloto de IA que ayuda a clasificar y resolver casos.

> **Estado:** en construcción. Proyecto personal de aprendizaje y portafolio. Todos los datos son sintéticos.

## Qué hará (hoja de ruta)

1. API de disputas: crear y consultar ✅ (ver abajo); cambiar de estado (abierta → en revisión → resuelta / rechazada) pendiente.
2. Persistencia en PostgreSQL con migraciones.
3. Webhook de entrada para eventos externos.
4. RAG sobre políticas de disputa, con citas.
5. Agente (LangGraph) que clasifica y propone una resolución.
6. Servidor MCP de solo lectura.
7. Evaluación con un conjunto de casos, observabilidad con Langfuse, guardrails (PII, prompt injection).

Cada ítem se marcará aquí solo cuando exista y tenga pruebas.

## Qué existe hoy

Dos endpoints, con pruebas automáticas:

| Método y ruta | Qué hace | Respuestas |
|---|---|---|
| `POST /disputes` | Abre una disputa. Siempre nace en estado `open`. | `201` con la disputa y el encabezado `Location`; `422` si la entrada es inválida |
| `GET /disputes/{dispute_id}` | Consulta una disputa por id. | `200`; `404` si no existe; `422` si el id no es un UUID |

Datos de entrada: `transaction_id`, `customer_id`, `amount` (mayor que 0, hasta 2 decimales y 12 dígitos), `currency` (3 letras mayúsculas), `reason` (`duplicate_charge`, `unrecognized_charge`, `product_not_received`, `incorrect_amount`, `devolution`) y `description` opcional (hasta 1000 caracteres). Los campos desconocidos, como `state`, se rechazan.

Todos los errores tienen el mismo formato:

```json
{"error": {"code": "validation_error", "message": "Request validation failed",
           "details": [{"field": "amount", "message": "Input should be greater than 0"}]}}
```

**Límites actuales:**
- Las disputas se guardan **en memoria**: se pierden al reiniciar el servidor. La persistencia en PostgreSQL es el siguiente paso de la hoja de ruta y aún no existe.
- No hay autenticación ni se verifica que la transacción exista.
- No se puede cambiar el estado de una disputa.

Detalle de la especificación: [`specs/001-create-and-get-dispute/`](specs/001-create-and-get-dispute/).

## Requisitos
- Python 3.12 y [uv](https://docs.astral.sh/uv/)
- Docker (para PostgreSQL)

## Cómo correrlo
```bash
uv sync
uv run uvicorn disputes.main:app --reload
# http://127.0.0.1:8000/docs
uv run pytest
```

Base de datos local (el servicio todavía no la usa; está lista para la feature de persistencia):
```bash
cp .env.example .env
docker compose up -d postgres
```

## Relación con otros proyectos
Independiente de `Bank` (arquitectura de eventos en .NET). Más adelante podrá consultar el estado de una transferencia en modo solo lectura.
