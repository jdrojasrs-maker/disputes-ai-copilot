# Disputes AI Copilot

![CI](https://github.com/OWNER/disputes-ai-copilot/actions/workflows/ci.yml/badge.svg)

Servicio **FastAPI** para gestionar disputas de transacciones (un cliente reclama un cobro), con un copiloto de IA que ayuda a clasificar y resolver casos.

> **Estado:** en construcción. Proyecto personal de aprendizaje y portafolio. Todos los datos son sintéticos.

## Qué hará (hoja de ruta)

1. API de disputas: crear, consultar y cambiar de estado (abierta → en revisión → resuelta / rechazada).
2. Persistencia en PostgreSQL con migraciones.
3. Webhook de entrada para eventos externos.
4. RAG sobre políticas de disputa, con citas.
5. Agente (LangGraph) que clasifica y propone una resolución.
6. Servidor MCP de solo lectura.
7. Evaluación con un conjunto de casos, observabilidad con Langfuse, guardrails (PII, prompt injection).

Cada ítem se marcará aquí solo cuando exista y tenga pruebas.

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

Base de datos local:
```bash
cp .env.example .env
docker compose up -d postgres
```

## Relación con otros proyectos
Independiente de `Bank` (arquitectura de eventos en .NET). Más adelante podrá consultar el estado de una transferencia en modo solo lectura.
