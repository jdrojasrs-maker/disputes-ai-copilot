# CLAUDE.md — disputes-ai-copilot

Servicio FastAPI de **disputas de transacciones** con un copiloto de IA (RAG, agente LangGraph, MCP, evals, Langfuse). Proyecto personal de portafolio. Es independiente de `Bank` (otro repo): no modificar Bank desde aquí.

## Stack
Python 3.12, FastAPI, Pydantic v2, PostgreSQL (SQLAlchemy async + Alembic, aún por agregar), pytest, ruff, uv, Docker Compose.

## Comandos
- Instalar: `uv sync`
- Servidor: `uv run uvicorn disputes.main:app --reload`
- Pruebas: `uv run pytest`
- Lint: `uv run ruff check .`
- Postgres local: `docker compose up -d postgres`

## Reglas de trabajo
- Un tema y un entregable por sesión. Trabajo por ramas y PRs hacia `develop`; `main` solo recibe merges de `develop`.
- El dueño del proyecto escribe la lógica central (modelos, endpoints, estados); la IA explica, plantea la tarea y revisa. Antes de cada commit con código generado por IA, el dueño debe poder explicarlo línea por línea.
- Pruebas primero (rojo, luego verde). Specs con GitHub Spec Kit en el repo.
- No afirmar en README/CV nada que no exista y esté probado. No inventar cifras: medir.
- Nunca versionar claves ni datos reales de clientes. Todo dato de ejemplo es sintético.
- Si dudas de una API o librería, verifica en la documentación oficial; no inventes.
