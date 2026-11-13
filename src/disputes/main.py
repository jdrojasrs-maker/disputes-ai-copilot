from fastapi import FastAPI

from disputes.errors import register_error_handlers
from disputes.routes import router

app = FastAPI(title="Disputes AI Copilot", version="0.1.0")
register_error_handlers(app)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
