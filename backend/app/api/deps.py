"""Dependencias de FastAPI: autenticación, autorización por rol y armado de los casos de uso.

Aquí se conectan los puertos con sus adaptadores del MVP. Las pruebas sustituyen los
adaptadores externos (ERP, reloj) sobrescribiendo estas dependencias.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.adapters.clock import SystemClock
from app.adapters.erp_http import ErpHttpAdapter
from app.adapters.local_storage import LocalStorageAdapter
from app.adapters.sql_misc import SqlCustomerAdapter
from app.adapters.weasyprint_doc import WeasyPrintDocumentAdapter
from app.application.approvals import ApprovalService
from app.application.followup import FollowUpService
from app.application.kpis import KpiService
from app.application.quotes import QuoteService
from app.domain.parties import Actor, Role
from app.infra.container import (
    build_approval_service,
    build_followup_service,
    build_kpi_service,
    build_quote_service,
)
from app.infra.db import get_session
from app.infra.models import Usuario
from app.infra.security import decode_access_token
from app.infra.settings import get_settings
from app.ports.external import CatalogPort, ClockPort, CustomerPort, DocumentPort, InventoryPort, StoragePort

bearer = HTTPBearer(auto_error=False)


# --- Adaptadores ----------------------------------------------------------------------


@lru_cache
def _erp_adapter() -> ErpHttpAdapter:
    return ErpHttpAdapter(httpx.Client(base_url=get_settings().erp_base_url, timeout=10))


def get_catalog() -> CatalogPort:
    return _erp_adapter()


def get_inventory() -> InventoryPort:
    return _erp_adapter()


def get_clock() -> ClockPort:
    return SystemClock()


@lru_cache
def get_documents() -> DocumentPort:
    return WeasyPrintDocumentAdapter()


@lru_cache
def get_storage() -> StoragePort:
    return LocalStorageAdapter(get_settings().storage_dir)


def get_customers(session: Session = Depends(get_session)) -> CustomerPort:
    return SqlCustomerAdapter(session)


def get_quote_service(
    session: Session = Depends(get_session),
    catalog: CatalogPort = Depends(get_catalog),
    inventory: InventoryPort = Depends(get_inventory),
    clock: ClockPort = Depends(get_clock),
    documents: DocumentPort = Depends(get_documents),
    storage: StoragePort = Depends(get_storage),
) -> QuoteService:
    return build_quote_service(session, catalog, inventory, clock, documents, storage)


def get_kpi_service(session: Session = Depends(get_session), clock: ClockPort = Depends(get_clock)) -> KpiService:
    return build_kpi_service(session, clock)


def get_approval_service(
    session: Session = Depends(get_session), clock: ClockPort = Depends(get_clock)
) -> ApprovalService:
    return build_approval_service(session, clock)


def get_followup_service(
    session: Session = Depends(get_session), clock: ClockPort = Depends(get_clock)
) -> FollowUpService:
    return build_followup_service(session, clock)


# --- Autenticación y roles ------------------------------------------------------------


@dataclass(frozen=True)
class CurrentUser:
    id: int
    usuario: str
    nombre: str
    rol: Role

    @property
    def actor(self) -> Actor:
        return Actor(id=self.id, rol=self.rol)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> CurrentUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión inválida o expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    user = session.get(Usuario, user_id) if user_id is not None else None
    # Se consulta el usuario en cada petición: desactivarlo corta el acceso de inmediato.
    if user is None or not user.activo:
        raise unauthorized
    return CurrentUser(id=user.id, usuario=user.usuario, nombre=user.nombre, rol=Role(user.rol))


def require_roles(*roles: Role) -> Callable[..., CurrentUser]:
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.rol not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Su rol no tiene permiso para esta acción")
        return user

    return dependency
