# Imagen única para alojar la demo en Render: Nginx (interfaz), API y ERP simulado en un
# solo contenedor. Solo cambia el empaquetado; el código es el mismo que usa Docker Compose.
# El contexto de construcción es la raíz del repositorio.

FROM node:22-alpine AS web
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Pango y DejaVu los necesita WeasyPrint; Nginx sirve la interfaz y reenvía /api.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/default

# Las dependencias del ERP simulado son un subconjunto de las del backend.
COPY backend/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

COPY backend/ /srv/backend/
COPY erp-mock/ /srv/erp-mock/
COPY --from=web /app/dist /usr/share/nginx/html
COPY deploy/render/nginx.conf /etc/nginx/cotiza.conf.template
COPY deploy/render/start.sh /srv/start.sh

CMD ["sh", "/srv/start.sh"]
