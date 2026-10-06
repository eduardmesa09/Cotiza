from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración técnica, leída de variables de entorno.

    Los parámetros de negocio (descuentos, márgenes, plazos) no van aquí: viven en la base
    de datos y los administra el rol de pricing.
    """

    database_url: str = "postgresql+psycopg://cotiza:cotiza@localhost:5433/cotiza"
    erp_base_url: str = "http://localhost:8001"
    jwt_secret: str = "solo-para-demo-cambiar-en-produccion"
    jwt_expire_minutes: int = 480
    storage_dir: str = "./storage"
    # El planificador de plazos corre dentro de la API; las pruebas lo apagan.
    scheduler_enabled: bool = True
    # Costo de bcrypt. Las pruebas lo bajan para no gastar segundos en cada contraseña.
    bcrypt_rounds: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
