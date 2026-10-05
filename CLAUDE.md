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
- Commits pequeños y descriptivos, en español.
- Se trabaja por fases; al terminar cada una se detiene para revisión.

## Comandos

Disponibles a partir de la Fase 1.

```bash
docker compose up --build        # levanta todo, con migraciones y semillas
docker compose down -v           # borra también la base de datos
make test                        # pytest + Vitest
docker compose run --rm api pytest            # equivalente sin make (Windows)
docker compose run --rm api pytest tests/unit # solo dominio, sin BD ni red
docker compose run --rm api alembic revision --autogenerate -m "mensaje"
```

## Fases

0. `CLAUDE.md`.
1. Esqueleto, Docker Compose, BD y migraciones, `erp-mock` con datos y semillas.
2. Dominio: motor de reglas, máquina de estados, tiempo hábil, con tests.
3. API, adaptadores, auth y roles (E1, E2, E3, E5).
4. Aprobaciones, SLA, escalamiento, seguimiento, vigencia y versiones (E4, E6–E10).
5. PDF y KPIs.
6. Frontend.
7. Datos de demo, README y pulido.
