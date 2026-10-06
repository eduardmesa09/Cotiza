"""Adaptador MVP de StoragePort: archivos en un volumen local. En producción sería Amazon S3."""

from pathlib import Path

from app.domain.errors import NotFoundError


class LocalStorageAdapter:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).resolve()

    def _path(self, ruta: str) -> Path:
        path = (self.base_dir / ruta).resolve()
        # Nunca se lee ni se escribe fuera de la carpeta de almacenamiento.
        if not path.is_relative_to(self.base_dir):
            raise NotFoundError("Ruta de archivo inválida")
        return path

    def save(self, nombre: str, contenido: bytes) -> str:
        path = self._path(nombre)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contenido)
        return nombre

    def read(self, ruta: str) -> bytes:
        path = self._path(ruta)
        if not path.is_file():
            raise NotFoundError("El archivo no existe")
        return path.read_bytes()
