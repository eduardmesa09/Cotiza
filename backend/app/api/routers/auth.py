from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.api.schemas import LoginIn, TokenOut, UserOut
from app.infra.db import get_session
from app.infra.models import Usuario
from app.infra.security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, session: Session = Depends(get_session)) -> dict:
    user = session.scalar(select(Usuario).where(Usuario.usuario == body.usuario.strip().lower()))
    # Mismo mensaje para usuario inexistente, inactivo o contraseña errada: no se revela cuál falló.
    if user is None or not user.activo or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")
    return {"access_token": create_access_token(user.id, user.rol), "usuario": user}


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user
