# COTIZA+ — guía para trabajar en este repositorio

MVP académico (Gerencia de Operaciones en TI, Universidad de La Sabana) que automatiza el ciclo de cotización a canales de distribución de Intcomex Colombia. Debe demostrar que la elaboración de una cotización baja de 24 a ~7 minutos, con precio correcto por reglas, disponibilidad neta, aprobación con SLA y trazabilidad completa.

**Especificación:** `docs/COTIZA_Informe_Cap1-7_v3.docx`. Mandan las secciones 5.4 (alcance y criterios de aceptación), 6.5 (roles y permisos), 6.6 (reglas, algoritmo, escenarios E1–E10), 6.7 (KPIs), Figura 8 (estados) y 7.2.2–7.3 (contenedores, puertos y adaptadores). Lo que esté fuera de 5.4 no se construye.

**Principios:** simple, reproducible con un solo comando, demostrable en 5–10 minutos. Funcionar de punta a punta va antes que agregar funcionalidades. Ante una ambigüedad de la especificación, preguntar antes de asumir.

## Stack (no cambiar sin consultar)

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, WeasyPrint, APScheduler, JWT.
- Base de datos: PostgreSQL 16.
- Frontend: React, TypeScript, Vite, Tailwind CSS, servido por Nginx.
- ERP simulado: FastAPI independiente con datos de Faker (semilla fija).
- Docker Compose con 4 servicios: `frontend`, `api`, `db`, `erp-mock`.
- Pruebas: pytest (backend), Vitest (frontend).
- Nada de AWS: la arquitectura objetivo solo existe en el documento.

## Arquitectura: puertos y adaptadores (obligatorio)

```
backend/app/
  domain/        entidades, errores, pricing_engine (puro), state_machine, business_time (puro)
  application/   casos de uso
  ports/         interfaces
  adapters/      implementaciones MVP
  api/           routers FastAPI, esquemas, auth y roles
  infra/         settings, BD, modelos ORM, scheduler, semillas
erp-mock/        servicio ERP simulado
frontend/        interfaz en español
```

- `domain/` y `application/` no importan FastAPI, SQLAlchemy, httpx ni WeasyPrint. Solo hablan con el exterior por puertos.
- Puertos: `CatalogPort`, `InventoryPort`, `CustomerPort`, `DocumentPort`, `StoragePort`, `NotificationPort`, `EventPort`, más `ClockPort` y los repositorios de persistencia.
- Adaptadores MVP: HTTP contra `erp-mock` (catálogo e inventario), datos semilla (canales), WeasyPrint + disco local (PDF y archivos), tabla de notificaciones, tabla de eventos.
- El motor de reglas es un módulo puro: recibe datos, devuelve resultados, no hace I/O ni lee el reloj. Todos los parámetros viven en BD; ningún porcentaje o plazo va escrito en el código.

## Reglas de negocio

Valores semilla; todos configurables en BD.

| Regla | Contenido |
|---|---|
| RN-01 | Parte del precio de lista vigente. Sin costo o sin lista → línea `NO_COTIZABLE`. |
| RN-02 | Descuento por nivel: Oro 6 %, Plata 4 %, Bronce 2 %. |
| RN-03 | Volumen por línea: 10–49 u → 2 %, 50–99 → 4 %, ≥100 → 6 %. |
| RN-04 | La promoción aplica solo si la fecha de la cotización está en su vigencia. Las vencidas se descartan y el descarte se registra. |
| RN-05 | Entre volumen y promoción, solo el mayor. El nivel sí se acumula. |
| RN-06 | Descuento adicional por línea propuesto por el ejecutivo; siempre reevalúa el margen. |
| RN-07 | Margen de alguna línea < mínimo de su categoría → requiere aprobación y la emisión se bloquea. |
| RN-08 | Precio < costo → `BAJO_COSTO`: no emitible ni con aprobación. |
| RN-09 | SLA de aprobación de 1 hora hábil; al vencer escala al gerente y notifica. Configurable en minutos. |
| RN-10 | Disponible = existencias − comprometido en cotizaciones emitidas y vigentes. Cantidad > disponible → `bajo_pedido`; no bloquea. |
| RN-11 | Vigencia: 7 días calendario o fin de la promoción aplicada, lo primero. |
| RN-12 | A las 48 h de emitida sin cierre → tarea de seguimiento. Al vencer la vigencia → `VENCIDA` y libera inventario. Plazos configurables. |
| RN-13 | Al emitir se congelan los precios. Un cambio posterior crea una nueva versión recalculada. |
| RN-14 | USD, 2 decimales. |

Márgenes mínimos: Portátiles 8 %, Periféricos 12 %, Servidores 10 %, Redes 11 %, Impresión 9 %.

Algoritmo por línea, en este orden:

```
precio = lista
precio *= (1 - nivel)
precio *= (1 - max(vol, promo_vigente))
precio *= (1 - adicional)
redondear a 2 decimales          # único redondeo, Decimal HALF_UP
margen = (precio - costo) / precio
evaluar RN-08 y RN-07
calcular disponibilidad neta
guardar reglas aplicadas en la línea
```

Evaluación de la cotización: alguna línea `NO_COTIZABLE` o `BAJO_COSTO` → `NO_EMITIBLE`; alguna requiere aprobación → `REQUIERE_APROBACION`; si no → `LISTA_PARA_EMITIR`.

**Caso de prueba obligatorio:** costo 620, lista 800, Plata, 20 u, promo vigente 5 %, margen mínimo 8 % → precio 729.60, margen 15.02 %, total 14 592.00, sin aprobación. Con 9 % adicional → 663.94, margen 6.62 %, requiere aprobación.

## Máquina de estados (Figura 8)

```
BORRADOR ⇄ CALCULADA            calcular / editar líneas
CALCULADA → PENDIENTE_APROBACION solicitar aprobación (margen < mínimo)
PENDIENTE_APROBACION → CALCULADA rechazo
CALCULADA → EMITIDA             lista para emitir y el ejecutivo confirma
PENDIENTE_APROBACION → EMITIDA  aprobada y el ejecutivo confirma
EMITIDA → EN_SEGUIMIENTO        48 h sin respuesta
EMITIDA → GANADA | VENCIDA
EN_SEGUIMIENTO → GANADA | PERDIDA | VENCIDA
```

Toda otra transición lanza un error de dominio. Cada transición registra un evento inmutable (tipo, cotización, usuario, timestamp, payload); la tabla de eventos solo admite inserciones y es la fuente de los KPIs.

## Decisiones de diseño acordadas

- **Solicitud de aprobación explícita:** "Calcular" deja la cotización en `CALCULADA` con su evaluación; el ejecutivo pulsa "Solicitar aprobación". Con `NO_EMITIBLE` no se puede solicitar.
- **Aprobada ≠ emitida:** tras aprobar, sigue en `PENDIENTE_APROBACION` hasta que el ejecutivo confirma. No se recalcula al emitir.
- **Versionado:** la nueva versión nace en `BORRADOR` (mismo número, versión+1). La anterior conserva sus precios, queda con bandera `reemplazada` y libera inventario. Cuenta como retrabajo.
- **Tiempo hábil:** función pura de minutos hábiles (L–V, jornada de 8 h, parámetros en BD) para SLA y KPIs, desactivable por parámetro para la demo.
- **Escalamiento:** reasigna la misma solicitud al gerente y notifica al gerente y al aprobador original. No es un segundo nivel de aprobación.
- **Promociones:** por referencia, con inicio y fin, sin vigencias superpuestas para la misma referencia.
- **Inventario comprometido:** min(cantidad, disponible) por línea al emitir, mientras esté `EMITIDA` o `EN_SEGUIMIENTO`, vigente y no reemplazada.
- **Vigencia:** min(emisión + 7 días, fin más temprano de las promociones efectivamente aplicadas).
- **Planificador:** un job de APScheduler por intervalo que busca en BD plazos vencidos (SLA, 48 h, vigencia). La API corre con un solo worker.
- **"Mantener en seguimiento":** cierra la tarea y programa otra con el mismo plazo.
- **Empate entre volumen y promoción (RN-05):** gana el volumen, porque no acorta la vigencia.
- **Margen mínimo (RN-07):** se compara el margen ya redondeado a 4 decimales, que es el que ve el usuario; un margen igual al mínimo no requiere aprobación.
- **Recalcular:** `CALCULADA → CALCULADA` está permitido para refrescar precios y disponibilidad sin editar (no aparece en la Figura 8).
- **Promoción vencida entre el cálculo y la emisión:** la emisión falla con `ExpiredPromotionError` y hay que recalcular.
- **Festivos:** el tiempo hábil no los modela.

## Dónde vive cada regla (dominio)

- `domain/pricing_engine.py`: RN-01 a RN-08, RN-10, RN-14; `calculate_line`, `evaluate_quote`, `quote_total`.
- `domain/state_machine.py`: estados, acciones y `next_state`; `allowed_actions` sirve para habilitar botones.
- `domain/business_time.py`: `business_time_between` y `add_business_time`.
- `domain/deadlines.py`: `approval_due` (RN-09), `valid_until` (RN-11), `follow_up_due` (RN-12).
- `tests/unit/test_architecture.py` falla si `domain/`, `application/` o `ports/` importan infraestructura, o si el dominio lee el reloj.

## Capas del backend (desde la Fase 3)

- `application/quotes.py`: `QuoteService` con los casos de uso crear, editar, calcular, emitir y consultar. Aquí se validan rol y propiedad de la cotización.
- `ports/external.py` y `ports/repositories.py`: interfaces (`Protocol`). `adapters/`: `erp_http.py` (catálogo e inventario), `sql_repositories.py` (cotizaciones y parámetros), `sql_misc.py` (canales, eventos, notificaciones), `clock.py`.
- `api/deps.py` conecta puertos con adaptadores y resuelve autenticación (`get_current_user`, `require_roles`). `api/routers/`: `auth`, `catalog`, `quotes`, `pricing`, `users`.
- `main.py` traduce los errores de dominio a HTTP: no existe 404, sin permiso 403, transición inválida 409, datos inválidos 422, ERP caído 503.
- Las rutas llaman al caso de uso y luego hacen `session.commit()`; los adaptadores solo hacen `flush`.
- La administración de pricing y de usuarios es gestión de datos sin flujo: sus rutas usan el ORM directamente. Las reglas de calidad de promociones sí están en `domain/promotions.py`.
- En la API los porcentajes viajan como fracción (`0.04` = 4 %) y los importes como texto decimal (`"729.60"`).
- La caducidad del JWT usa la hora real del sistema, no `ClockPort`.

### Después de emitir (Fase 4)

- `application/approvals.py` (`ApprovalService`): solicitar, cola, aprobar o rechazar, escalar. `application/followup.py` (`FollowUpService`): tareas, cerrar como ganada o perdida, mantener en seguimiento, nueva versión, vencer. `application/deadlines.py` (`DeadlineService.process`): un ciclo de plazos, idempotente.
- `infra/scheduler.py`: APScheduler llama a `DeadlineService.process` cada `planificador_intervalo_segundos` (se lee al arrancar). Se apaga con `SCHEDULER_ENABLED=false`; las pruebas lo apagan y usan la fixture `run_deadlines`.
- `infra/container.py` es el único lugar que decide qué adaptador implementa cada puerto.
- Cola de aprobaciones: el aprobador ve todas las pendientes; el gerente, solo las escaladas. Ambos pueden resolver cualquiera. Orden: antigüedad y luego monto.
- `acciones_permitidas` son las transiciones posibles de la máquina de estados, sin filtrar por rol; la interfaz combina eso con el rol del usuario.
- Una versión reemplazada conserva su estado (`EMITIDA` o `EN_SEGUIMIENTO`) con `reemplazada = true`: no compromete inventario, no genera seguimiento ni vence, y no admite más acciones.
- Al cerrarse (ganada, perdida o vencida) la cotización deja de comprometer inventario; `cantidad_comprometida` se conserva en la línea como registro.
- Rutas nuevas: `POST /cotizaciones/{id}/solicitar-aprobacion | cerrar | nueva-version`, `GET /aprobaciones`, `POST /aprobaciones/{id}/aprobar | rechazar`, `GET /seguimiento`, `POST /seguimiento/{id}/resolver`, `GET /notificaciones`.
- Para la demo: bajar `sla_aprobacion_minutos`, `seguimiento_minutos` y `vigencia_minutos` y poner `horario_habil_activo` en `false` desde la administración de parámetros.

### PDF e indicadores (Fase 5)

- Al emitir, `QuoteService.issue` arma los datos con `application/documents.py`, los dibuja `adapters/weasyprint_doc.py` (plantilla única `adapters/templates/cotizacion.html`) y los guarda `adapters/local_storage.py` en `STORAGE_DIR` como `<numero>-v<version>.pdf`. Si el PDF falla, la emisión completa se revierte.
- El documento es lo que ve el canal: nunca incluye costo ni margen. Las fechas van en la zona horaria de la operación.
- `GET /cotizaciones/{id}/pdf` lo descarga quien puede consultar la cotización.
- `domain/kpis.py` (`compute_kpis`) calcula los indicadores solo con la lista de eventos; incluye línea base AS-IS y meta. `GET /kpis`: el ejecutivo ve los propios; aprobador, gerente y pricing, todos; admin no.
- Los tiempos de los KPIs son hábiles. Fuera del horario hábil dan 0: para demostrar a deshoras hay que poner `horario_habil_activo` en `false`.
- K11b se calcula sobre las solicitudes resueltas (una pendiente aún dentro de su SLA no cuenta como incumplida).
- Las pruebas usan `documents` (`FakeDocuments`, guarda los datos recibidos) y `storage` (`FakeStorage`); WeasyPrint real solo se ejercita en `tests/adapters/test_documents.py`.
- La imagen de la API instala Pango y la fuente DejaVu, que WeasyPrint necesita.

### Frontend (Fase 6)

- `frontend/src/`: `lib/` (`api.ts` cliente con token, `format.ts`, `permissions.ts`, `useApi.ts`, `types.ts`), `auth/AuthContext.tsx`, `components/` (`ui.tsx` piezas comunes, `Layout.tsx`, `LinesTable.tsx`, `ProductSearch.tsx`, `QuoteHistory.tsx`) y `pages/`.
- Estilo: navegación superior en píldoras, tarjetas blancas de esquinas amplias sobre fondo gris claro, cifras grandes. La paleta está en `src/index.css` como tokens de Tailwind (`bg-brand`, `text-ink`, `border-line`, `text-muted`, `bg-navy`, `text-accent`, `text-ok`, `text-bad`…): usar los tokens, no colores sueltos. Tipografía Plus Jakarta Sans, empaquetada (funciona sin internet).
- `lib/permissions.ts` define el menú por rol, la pantalla de inicio y `quoteActions`, que combina rol, propiedad y `acciones_permitidas` para decidir qué botones mostrar. «Emitir» exige además que no haya cambios sin calcular.
- `/cotizaciones/:id` sirve para una existente y para `nueva`; es una sola ruta a propósito, para que la pantalla no se vuelva a montar al calcular por primera vez.
- «Calcular» guarda (crea o actualiza) y calcula en un solo paso. No hay «guardar borrador» aparte.
- Las pantallas con plazos se refrescan solas: aprobaciones cada 10 s, notificaciones y seguimiento cada 20 s, lista y tablero cada 30 s.
- En las barras del tablero, la línea base usa `chart-base` (`#E0961A`), un paso más oscuro que el naranja de la paleta, que como barra es demasiado claro. Un indicador sin meta (K10) muestra la variación sin calificarla.
- Pruebas: `src/test/helpers.tsx` trae `mockApi` (simula `fetch` por ruta), `renderApp` y datos de ejemplo (`quote()`, `line()`, `kpi()`).

### Demo y cierre (Fase 7)

- `infra/demo.py` (`python -m app.infra.demo`, o `make demo`): recrea unas tres semanas de operación ejecutando los casos de uso reales con un `SettableClock`. Cada cotización es un generador que cede el momento de su siguiente paso; el simulador los ejecuta en orden cronológico y procesa los plazos antes de cada paso. Solo corre sobre una base sin cotizaciones. Crea el usuario `ejecutivo2`.
- Las promociones semilla se limitan para que, aun con nivel Oro, no dejen el margen bajo el mínimo de la categoría: una cotización estándar no debe pedir aprobación solo por la promoción.
- `README.md` es el entregable de documentación: inicio rápido, usuarios, guion de demo, arquitectura, pruebas y limitaciones. Si cambia un comando, un usuario o un parámetro de demo, actualizarlo.

### Pruebas

- `tests/conftest.py` ofrece: `db` (sesión con semillas), `client` (API con ERP y reloj falsos), `erp` (`FakeErp`, catálogo en memoria), `clock` (`FakeClock`, se adelanta con `clock.advance(minutes=5)`), `as_user("ejecutivo")` (cabeceras) y `demo_channel`, `run_deadlines()` (un ciclo del planificador con el reloj de la prueba) y `notifications("gerente")`.
- `tests/helpers.py` tiene atajos: `create_quote`, `calculate`, `issue`, `create_calculated`, `line`.
- `tests/scenarios/` tiene un archivo por escenario E1–E10; recorren la API completa.
- Tras un `session.commit()` del código probado, los datos de la prueba siguen ahí: la sesión usa savepoints y todo se revierte al final.

## Roles y permisos (Tabla 32)

| Acción | Ejecutivo | Aprobador | Gerente | Pricing | Admin |
|---|---|---|---|---|---|
| Crear y editar cotizaciones propias | Sí | No | No | No | No |
| Proponer descuento adicional | Sí | No | No | No | No |
| Aprobar o rechazar (comentario obligatorio) | No | Sí | Sí | No | No |
| Confirmar emisión | Sí | No | No | No | No |
| Consultar todas las cotizaciones | No | Sí | Sí | Sí | No |
| Administrar reglas y promociones | No | No | No | Sí | No |
| Tablero de indicadores | Propios | Sí | Sí | Sí | No |
| Gestionar usuarios | No | No | No | No | Sí |

Segregación de funciones: quien propone un descuento no puede aprobarlo. Los permisos se validan en el backend; la interfaz solo los refleja.

## KPIs del tablero (desde la tabla de eventos)

| KPI | Fórmula | Línea base AS-IS |
|---|---|---|
| K2 Tiempo de elaboración | emisión − creación − tiempo en aprobación | 24 min |
| K3 Tiempo de respuesta | emisión − recepción, en horas hábiles | 6,4 h |
| K4 Cumplimiento del SLA | cotizaciones con K3 ≤ 4 h ÷ emitidas | 58 % |
| K11 Espera de aprobación | resolución − solicitud | 5,2 h |
| K11b Aprobaciones en SLA | resueltas en ≤ 1 h ÷ solicitadas | — |
| K8 Retrabajo | con nueva versión tras emisión ÷ emitidas | 12 % |
| K13 Conversión | ganadas ÷ (ganadas + perdidas + vencidas) | 31 % |
| K14 Seguimiento | emitidas con tarea de seguimiento o cierre ÷ emitidas | 54 % |

## Fuera del MVP

Integración real con ERP/CRM/portal, conversión a orden, envío por correo, firma electrónica, aprobación de varios niveles, múltiples monedas, interpretación asistida de solicitudes (6.4.3), revisión de reglas por una segunda persona, caché de existencias, K5 y K7, y todo componente de AWS.

## Convenciones

- Identificadores de código en inglés; términos de dominio de la especificación en español sin tildes (`BORRADOR`, `PENDIENTE_APROBACION`, `bajo_pedido`, nombres de tablas). Interfaz y mensajes al usuario en español.
- Dinero y porcentajes con `Decimal`, nunca `float`.
- Cada entidad o módulo que se cree o corrija va con su test. Los escenarios E1–E10 tienen un test cada uno.
- El tiempo se obtiene siempre de `ClockPort`; nada de `datetime.now()` en dominio ni casos de uso.
- Comentarios solo donde aporten (el porqué, la regla RN que se aplica).
- Los commits los hace Eduard al revisar cada fase; no confirmar ni crear ramas por cuenta propia.
- Se trabaja por fases; al terminar cada una se detiene para revisión.

## Comandos

```bash
docker compose up --build        # levanta todo, con migraciones y semillas
docker compose down -v           # borra también la base de datos (regenera semillas)
make test                        # todas las pruebas; en Windows sin make: .\scripts	est.ps1

# Pruebas por servicio (reconstruir la imagen antes: el código se copia, no se monta)
docker compose build api && docker compose run --rm --no-deps api pytest
docker compose run --rm --no-deps api pytest tests/unit   # solo dominio: no necesita base de datos
docker compose build erp-mock && docker compose run --rm --no-deps erp-mock pytest
docker compose --profile test build frontend-test && docker compose --profile test run --rm frontend-test
cd frontend && npm test          # Vitest local, más rápido para iterar

# Nueva migración tras cambiar app/infra/models.py (monta versions/ para que el archivo quede en el repo)
docker compose run --rm --no-deps -v "$PWD/backend/alembic/versions:/app/alembic/versions" api   alembic revision --autogenerate -m "mensaje"
```

- Puertos: web 8080, API 8000 (`/api/docs`), ERP simulado 8001 (`/docs`), PostgreSQL 5433.
- Las pruebas del backend necesitan el servicio `db` arriba; usan una base aparte, `cotiza_test`, y cada prueba se revierte.
- `tests/infra/test_migrations.py` falla si los modelos y las migraciones no coinciden.
- Usuarios semilla: `ejecutivo`, `aprobador`, `gerente`, `pricing`, `admin`; contraseña `Cotiza2026*`.
- Referencia de demo `POR-DEMO01` (costo 620, lista 800, promoción vigente del 5 %) y canal de demo "Soluciones Andinas TI S.A.S. (demo)", nivel Plata: reproducen el caso de prueba obligatorio.

## Fases

Todas terminadas.

0. `CLAUDE.md`.
1. Esqueleto, Docker Compose, BD y migraciones, `erp-mock` con datos y semillas.
2. Dominio: motor de reglas, máquina de estados, tiempo hábil, con tests.
3. API, adaptadores, auth y roles (E1, E2, E3, E5).
4. Aprobaciones, SLA, escalamiento, seguimiento, vigencia y versiones (E4, E6–E10).
5. PDF y KPIs.
6. Frontend.
7. Datos de demo, README y pulido.
