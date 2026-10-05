from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infra.db import get_session

app = FastAPI(
    title="COTIZA+ API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.get("/api/health")
def health(session: Session = Depends(get_session)) -> dict:
    """Confirma que la API responde y que la base de datos está accesible."""
    session.execute(text("SELECT 1"))
    return {"status": "ok"}
