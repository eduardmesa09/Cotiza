"""Gestión de usuarios y roles: exclusiva del administrador del sistema (Tabla 32)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_clock, require_roles
from app.api.schemas import UserAdminOut, UserCreateIn, UserUpdateIn
from app.domain.parties import Role
from app.infra.db import get_session
from app.infra.models import Usuario
from app.infra.security import hash_password
from app.ports.external import ClockPort

router = APIRouter(prefix="/api/usuarios", tags=["Usuarios"])

admin_only = require_roles(Role.ADMIN)


@router.get("", response_model=list[UserAdminOut])
def list_users(session: Session = Depends(get_session), _: CurrentUser = Depends(admin_only)) -> list:
    return list(session.scalars(select(Usuario).order_by(Usuario.usuario)))


@router.post("", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateIn,
    session: Session = Depends(get_session),
    clock: ClockPort = Depends(get_clock),
    _: CurrentUser = Depends(admin_only),
) -> Usuario:
    if session.scalar(select(Usuario).where(Usuario.usuario == body.usuario)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El usuario '{body.usuario}' ya existe")
    row = Usuario(
        usuario=body.usuario,
        nombre=body.nombre,
        email=body.email,
        rol=body.rol,
        password_hash=hash_password(body.password),
        activo=True,
        creado_en=clock.now(),
    )
    session.add(row)
    session.commit()
    return row


@router.put("/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: int,
    body: UserUpdateIn,
    session: Session = Depends(get_session),
    admin: CurrentUser = Depends(admin_only),
) -> Usuario:
    row = session.get(Usuario, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El usuario no existe")
    # Un administrador no puede dejarse a sí mismo sin acceso: el sistema quedaría sin quien gestione usuarios.
    if row.id == admin.id and (body.activo is False or (body.rol is not None and body.rol is not Role.ADMIN)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No puede desactivarse ni cambiar su propio rol"
        )
    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in changes.items():
        if value is not None:
            setattr(row, field, value)
    if body.password:
        row.password_hash = hash_password(body.password)
    session.commit()
    return row
