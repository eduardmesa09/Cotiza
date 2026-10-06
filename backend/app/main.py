from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routers import auth, catalog, pricing, quotes, users, workflow
from app.domain.approval import CommentRequiredError
from app.domain.errors import (
    DomainError,
    ExternalServiceError,
    InvalidLineError,
    InvalidTransitionError,
    NotFoundError,
    PermissionDeniedError,
)
from app.domain.promotions import InvalidPromotionError
from app.infra.db import get_session
from app.infra.settings import get_settings



@asynccontextmanager
async def lifespan(_: FastAPI):
    """Arranca el planificador de plazos junto con la API y lo detiene al apagar."""
    scheduler = None
    if get_settings().scheduler_enabled:
        from app.infra.scheduler import start_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="COTIZA+ API",
    version="0.4.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# Cada error de dominio se traduce a un código HTTP; el mensaje llega tal cual a la interfaz.
ERROR_STATUS: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    InvalidTransitionError: status.HTTP_409_CONFLICT,
    InvalidLineError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidPromotionError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    CommentRequiredError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ExternalServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


@app.exception_handler(DomainError)
def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
    code = next((c for t, c in ERROR_STATUS.items() if isinstance(exc, t)), status.HTTP_409_CONFLICT)
    return JSONResponse(status_code=code, content={"detail": str(exc)})


for router in (auth.router, catalog.router, quotes.router, workflow.router, pricing.router, users.router):
    app.include_router(router)


@app.get("/api/health", tags=["Sistema"])
def health(session: Session = Depends(get_session)) -> dict:
    """Confirma que la API responde y que la base de datos está accesible."""
    session.execute(text("SELECT 1"))
    return {"status": "ok"}
