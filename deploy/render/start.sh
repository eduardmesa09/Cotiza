#!/bin/sh
# Arranque del contenedor único de Render: Nginx, ERP simulado, migraciones, semillas y API.
set -e

PORT="${PORT:-10000}"
# Render entrega la conexión como postgresql://…; SQLAlchemy necesita indicar el controlador.
export DATABASE_URL="postgresql+psycopg://${DATABASE_URL#*://}"
export ERP_BASE_URL="http://127.0.0.1:8001"

# Nginx primero: Render da el servicio por iniciado cuando el puerto responde.
sed "s/__PORT__/${PORT}/" /etc/nginx/cotiza.conf.template > /etc/nginx/conf.d/default.conf
nginx

(cd /srv/erp-mock && exec uvicorn app.main:app --host 127.0.0.1 --port 8001) &
python - <<'EOF'
import time, urllib.request
for _ in range(60):
    try:
        urllib.request.urlopen("http://127.0.0.1:8001/health")
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("El ERP simulado no arrancó")
EOF

cd /srv/backend
alembic upgrade head
python -m app.infra.seeds
if [ "${LOAD_DEMO:-false}" = "true" ]; then
    # Solo carga algo la primera vez: con cotizaciones en la base, el script no hace nada.
    python -m app.infra.demo || echo "Escenario de demo omitido."
fi

exec uvicorn app.main:app --host 127.0.0.1 --port 8000
