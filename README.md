# COTIZA+

Producto mínimo viable que automatiza el ciclo de cotización a canales de distribución de
Intcomex Colombia: del registro de la solicitud a la cotización emitida en PDF, con precio
calculado por reglas, disponibilidad neta, aprobación con plazo, seguimiento y trazabilidad.

Proyecto del curso Gerencia de Operaciones en TI, Universidad de La Sabana (2026-2).
El diseño completo está en [docs/COTIZA_Informe_Cap1-7_v3.docx](docs/COTIZA_Informe_Cap1-7_v3.docx).

> Prototipo académico. Todos los datos (catálogo, canales, precios, usuarios) son simulados.
> No se conecta a ningún sistema de Intcomex.

## Qué demuestra

El proceso manual consume 24 minutos por cotización, repartidos entre cinco fuentes de
información. COTIZA+ consolida esas fuentes y ejecuta las reglas comerciales, de modo que el
ejecutivo solo registra la solicitud y valida el resultado.

| Indicador | Proceso manual | Meta |
|---|---|---|
| Tiempo de elaboración | 24 min | 7 min |
| Tiempo de respuesta al canal | 6,4 h | 1,5 h |
| Cumplimiento del SLA de 4 h | 58 % | 92 % |
| Espera por aprobación | 5,2 h | ≤ 1 h |

El tablero de la aplicación calcula estos indicadores a partir de su propio registro de
eventos y los compara con esta línea base.

## Inicio rápido

Requisito: [Docker Desktop](https://www.docker.com/products/docker-desktop/) en ejecución.

```bash
docker compose up --build
```

La primera vez tarda unos minutos mientras se construyen las imágenes. El arranque aplica
las migraciones de base de datos y carga los datos semilla automáticamente.

| Servicio | URL |
|---|---|
| Aplicación web | http://localhost:8080 |
| API (documentación interactiva) | http://localhost:8000/api/docs |
| ERP simulado (documentación) | http://localhost:8001/docs |

Para que el tablero tenga datos históricos, con el sistema arriba ejecute en otra terminal:

```bash
docker compose exec api python -m app.infra.demo      # o: make demo
```

Esto recrea unas tres semanas de operación (cerca de 100 cotizaciones) en medio minuto.
Solo corre sobre una base sin cotizaciones.

Otros comandos:

```bash
docker compose down        # detener
docker compose down -v     # detener y borrar la base de datos y los PDF (empezar de cero)
```

Si un puerto está ocupado, cámbielo con una variable de entorno, por ejemplo
`WEB_PORT=9090 docker compose up` (ver [.env.example](.env.example)).

## Usuarios de prueba

Todos usan la contraseña `Cotiza2026*`.

| Usuario | Rol | Qué hace |
|---|---|---|
| `ejecutivo` | Ejecutivo de cuenta | Crea, calcula y emite cotizaciones; propone descuentos; atiende seguimientos; ve sus indicadores |
| `aprobador` | Aprobador | Resuelve la cola de aprobaciones con comentario obligatorio |
| `gerente` | Gerente comercial | Recibe las aprobaciones escaladas; ve el tablero completo |
| `pricing` | Administrador de pricing | Mantiene promociones, márgenes mínimos, niveles de canal, escalas y plazos |
| `admin` | Administrador del sistema | Gestiona usuarios y parámetros |
| `ejecutivo2` | Ejecutivo de cuenta | Existe solo tras cargar el escenario de demo |

Quien propone un descuento no puede aprobarlo, quien administra las reglas no emite
cotizaciones y quien gestiona usuarios no participa del proceso comercial.

## Guion de demostración

Pensado para un video de 5 a 10 minutos. Antes de grabar:

1. `docker compose down -v` y `docker compose up --build` para partir de cero.
2. `docker compose exec api python -m app.infra.demo` para tener historia en el tablero.
3. Entre como `pricing` → **Reglas y promociones** → **Plazos** y ajuste:

   | Parámetro | Valor para la demo | Efecto |
   |---|---|---|
   | `horario_habil_activo` | `false` | Los plazos y tiempos corren en reloj real, a cualquier hora |
   | `sla_aprobacion_minutos` | `2` | El escalamiento ocurre a los 2 minutos |
   | `seguimiento_minutos` | `3` | La tarea de seguimiento aparece a los 3 minutos |
   | `vigencia_minutos` | `6` | La cotización vence a los 6 minutos |

   El planificador revisa los plazos cada 30 segundos: un vencimiento puede tardar hasta
   medio minuto en reflejarse. Sin el primer ajuste, fuera del horario de 09:00 a 17:00
   (lunes a viernes, hora de Bogotá) los tiempos del tablero se miden como cero.

### 1. Cotización estándar (el caso de los 7 minutos)

Como `ejecutivo`: **Nueva cotización**.

- Canal: *Soluciones Andinas TI S.A.S. (demo)*, nivel Plata.
- Busque `demo` y agregue `POR-DEMO01`; cantidad **20**.
- **Calcular**. Resultado: precio **729,60**, margen **15,02 %**, total **USD 14.592,00**.
- Despliegue la línea para ver las reglas aplicadas: lista 800 → nivel Plata 4 % → 768 →
  promoción vigente 5 % → 729,60 (la escala por volumen de 2 % no se acumula: aplica el mayor).
- **Emitir** y **Descargar PDF**. El historial de la derecha muestra cada paso con su hora.

Es el ejemplo de la sección 6.6.3 del informe.

### 2. Descuento que requiere aprobación

Nueva cotización con la misma referencia y cantidad, y **9** en *Desc. adicional*.

- **Calcular**: precio 663,94, margen **6,62 %**, por debajo del 8 % mínimo de Portátiles.
  El botón **Emitir** queda deshabilitado.
- **Solicitar aprobación**.
- Cierre sesión y entre como `aprobador`: la solicitud aparece con todo su contexto y el
  tiempo que queda de plazo. **Aprobar** con un comentario.
- Vuelva como `ejecutivo`: la campana avisa la aprobación. Abra la cotización y
  **Confirmar emisión**.

Variante: **Rechazar** con comentario; la cotización vuelve al ejecutivo, que baja el
descuento, recalcula y emite.

### 3. Plazo de aprobación vencido

Solicite otra aprobación y no la resuelva. A los 2 minutos (más hasta 30 segundos), entre
como `gerente`: la solicitud aparece en **Escalamientos**, marcada como escalada, y el
gerente y el aprobador reciben la notificación.

### 4. Controles que no se pueden saltar

- **Precio bajo el costo:** con **20** en *Desc. adicional* el precio (583,68) queda bajo el
  costo (620). La cotización no se puede emitir ni enviar a aprobación.
- **Bajo pedido:** pida más unidades de las disponibles; la línea se marca *Bajo pedido* con
  alerta, pero no impide emitir.
- **Disponibilidad neta:** tras emitir 20 unidades, una cotización nueva de la misma
  referencia ve 20 disponibles menos.
- **Referencia no cotizable:** busque `POR-00017` (no tiene costo cargado en el ERP); aparece
  marcada como *No cotizable* y no se puede agregar.

### 5. Seguimiento y vigencia

A los 3 minutos de emitida sin cierre, el `ejecutivo` recibe una tarea en **Seguimiento**:
**Ganada**, **Perdida** o **Mantener en seguimiento**. A los 6 minutos sin cierre, la
cotización pasa a *Vencida* y libera el inventario.

### 6. Precio congelado y nueva versión

Con una cotización emitida, cambie el precio de lista en el ERP simulado:

```bash
curl -X PATCH http://localhost:8001/products/POR-DEMO01/price \
  -H "Content-Type: application/json" -d '{"precio_lista": "900.00"}'
```

La cotización emitida conserva 729,60. **Nueva versión** crea la versión 2 en borrador; al
calcularla toma el precio nuevo (820,80), y la versión 1 queda marcada como reemplazada.

### 7. Administración de reglas

Como `pricing`: cree una promoción con vigencia, o cambie el margen mínimo de una categoría.
El siguiente cálculo ya usa el valor nuevo, sin reiniciar nada. Dos promociones con vigencias
superpuestas para la misma referencia se rechazan.

### 8. Tablero

Como `gerente`: **Indicadores**. Cada tarjeta compara el valor medido con la línea base del
proceso manual y con la meta. El `ejecutivo` ve solo los indicadores de sus cotizaciones.

## Arquitectura

```
                    ┌──────────────────────────┐
  Navegador ───────▶│ frontend (Nginx + React) │ :8080
                    └────────────┬─────────────┘
                                 │ /api
                    ┌────────────▼─────────────┐        ┌─────────────────────┐
                    │ api (FastAPI)            │───────▶│ erp-mock (FastAPI)  │ :8001
                    │  casos de uso + reglas   │  HTTP  │  catálogo, costos,  │
                    │  planificador de plazos  │        │  precios, existencias│
                    │  generación de PDF       │        └─────────────────────┘
                    └────────────┬─────────────┘ :8000
                                 │
                    ┌────────────▼─────────────┐
                    │ db (PostgreSQL 16)       │ :5433
                    └──────────────────────────┘
```

Cuatro contenedores. Cada uno corresponde a un componente de la arquitectura objetivo sobre
AWS descrita en el capítulo 7 del informe, que no forma parte de este MVP.

### Puertos y adaptadores

El núcleo (motor de reglas y casos de uso) no conoce la infraestructura: habla con el
exterior a través de interfaces. Pasar a producción es cambiar adaptadores, no la lógica.

| Puerto | Adaptador en el MVP | Adaptador objetivo |
|---|---|---|
| `CatalogPort`, `InventoryPort` | HTTP contra el ERP simulado | API del ERP por VPN |
| `CustomerPort` | Canales semilla en PostgreSQL | CRM |
| `DocumentPort` | Plantilla HTML + WeasyPrint | Worker asíncrono |
| `StoragePort` | Volumen local | Amazon S3 |
| `NotificationPort` | Notificaciones en la aplicación | Amazon SES |
| `EventPort` | Tabla de eventos de solo inserción | Amazon EventBridge |
| `ClockPort` | Reloj del sistema | — |

```
backend/app/
  domain/        motor de reglas, máquina de estados, tiempo hábil, plazos, indicadores (puro)
  application/   casos de uso
  ports/         interfaces
  adapters/      implementaciones del MVP
  api/           rutas HTTP, autenticación y permisos
  infra/         configuración, modelos, migraciones, planificador, semillas, demo
erp-mock/        ERP simulado
frontend/src/    interfaz web
```

Una prueba automática falla si el núcleo importa infraestructura.

### Reglas de negocio

Las catorce reglas del informe (RN-01 a RN-14) están en
[backend/app/domain/pricing_engine.py](backend/app/domain/pricing_engine.py),
[state_machine.py](backend/app/domain/state_machine.py) y
[deadlines.py](backend/app/domain/deadlines.py). Los porcentajes y plazos no están en el
código: viven en la base de datos y se cambian desde la aplicación.

El orden de cálculo de cada línea es fijo:

```
precio = precio de lista
precio = precio × (1 − descuento por nivel del canal)
precio = precio × (1 − el mayor entre escala por volumen y promoción vigente)
precio = precio × (1 − descuento adicional del ejecutivo)
redondear a 2 decimales
margen = (precio − costo) ÷ precio
```

### Estados de la cotización

```
BORRADOR ⇄ CALCULADA ─▶ PENDIENTE_APROBACION ─▶ EMITIDA ─▶ EN_SEGUIMIENTO ─▶ GANADA | PERDIDA | VENCIDA
              │  ▲ rechazo                         ▲   │
              └──┴─────────────────────────────────┘   └──▶ GANADA | VENCIDA
```

Cada transición registra un evento que no se puede modificar ni borrar (lo impide un
disparador en la base de datos). Ese registro es la fuente del historial y de los indicadores.

## Tecnologías

| Capa | Tecnología |
|---|---|
| Servicios | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, APScheduler |
| Base de datos | PostgreSQL 16 |
| Documento | WeasyPrint (HTML a PDF) |
| Autenticación | JWT con cinco roles |
| Interfaz | React, TypeScript, Vite, Tailwind CSS |
| Datos simulados | Faker |
| Despliegue | Docker Compose |
| Pruebas | pytest, Vitest |

## Pruebas

```bash
make test              # Linux, macOS o Windows con make
.\scripts\test.ps1     # Windows (PowerShell)
```

Corren dentro de Docker; no hace falta instalar Python ni Node. Por servicio:

```bash
docker compose build api && docker compose up -d --wait db
docker compose run --rm --no-deps api pytest                    # backend completo
docker compose run --rm --no-deps api pytest tests/unit         # solo reglas: sin base de datos
docker compose run --rm --no-deps api pytest tests/scenarios    # escenarios E1 a E10
docker compose run --rm --no-deps erp-mock pytest               # ERP simulado
docker compose --profile test run --rm frontend-test            # interfaz
```

Qué cubren:

- **Motor de reglas:** RN-01 a RN-14 y el caso del informe (729,60 · 15,02 % · 14.592,00; con
  9 % adicional, 663,94 · 6,62 % · requiere aprobación).
- **Máquina de estados:** las transiciones válidas y las 72 combinaciones inválidas.
- **Escenarios E1 a E10** de la sección 6.6.4, recorriendo la API completa
  ([backend/tests/scenarios/](backend/tests/scenarios/)).
- **Permisos** de la matriz por rol, adaptadores, migraciones, semillas, generación del PDF,
  indicadores y el escenario de demo.
- **Interfaz:** cuándo se puede emitir, alertas por línea, acceso por rol, formato.

## Limitaciones conocidas

- El escalamiento, el seguimiento y el vencimiento pueden tardar hasta 30 segundos en
  reflejarse, porque el planificador corre por intervalos.
- El tiempo hábil no considera festivos.
- No hay control de concurrencia sobre el inventario comprometido: dos emisiones simultáneas
  de la misma referencia podrían comprometer las mismas unidades.
- Los cambios hechos en el ERP simulado (precio, existencias) se pierden al reiniciar ese contenedor.
- Las promociones semilla se fechan respecto al día en que se crea la base; pasadas unas
  semanas, las vigentes irán venciendo. `docker compose down -v` las regenera.
- La tasa de conversión del tablero sale de datos simulados; en el informe es un indicador
  proyectado, verificable solo en operación real.

Fuera del alcance (sección 5.4 del informe): integración con sistemas reales, conversión a
orden de compra, envío por correo, firma electrónica, aprobación de varios niveles, múltiples
monedas y despliegue en AWS.

## Equipo

María Fernanda Rodríguez Chaparro · Laura Valentina Rairán Gavilán · Juan Pablo Vargas Jiménez ·
Eduard Meza Salazar. Docente: Mateo Barón Rojas.
