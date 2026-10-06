"""Indicadores operativos (sección 6.7), calculados solo a partir del registro de eventos.

Módulo puro: recibe la lista de eventos y el calendario hábil, y devuelve los indicadores
junto con la línea base AS-IS (Tabla 10) y la meta (Tabla 25) para compararlos.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.business_time import BusinessCalendar, business_time_between
from app.domain.events import Event, EventType

T = EventType

CREATION = {T.COTIZACION_CREADA, T.NUEVA_VERSION_CREADA}
RESOLUTION = {T.APROBACION_APROBADA, T.APROBACION_RECHAZADA}
CLOSURE = {T.COTIZACION_GANADA, T.COTIZACION_PERDIDA, T.COTIZACION_VENCIDA}
# Evidencia de que la cotización emitida no quedó abandonada (indicador K14).
FOLLOW_UP_EVIDENCE = {T.SEGUIMIENTO_PROGRAMADO, T.SEGUIMIENTO_INICIADO, T.COTIZACION_REEMPLAZADA} | CLOSURE


@dataclass(frozen=True)
class Kpi:
    codigo: str
    nombre: str
    valor: float | None  # None: todavía no hay datos para calcularlo
    unidad: str
    linea_base: float | None
    meta: float | None
    # "menor": mejora cuando baja; "mayor": mejora cuando sube.
    sentido: str
    muestra: int  # cuántos casos sustentan el valor
    formula: str


@dataclass(frozen=True)
class KpiReport:
    totales: dict[str, int]
    indicadores: list[Kpi]


def quote_owners(events: Sequence[Event]) -> dict[int, int]:
    """Ejecutivo de cada cotización: quien registró su creación."""
    return {
        e.cotizacion_id: e.usuario_id
        for e in events
        if e.tipo in CREATION and e.cotizacion_id is not None and e.usuario_id is not None
    }


def _average(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _percentage(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def compute_kpis(events: Sequence[Event], calendar: BusinessCalendar, sla_respuesta_minutos: int) -> KpiReport:
    by_quote: dict[int, list[Event]] = defaultdict(list)
    for event in sorted(events, key=lambda e: (e.ocurrido_en, e.id or 0)):
        if event.cotizacion_id is not None:
            by_quote[event.cotizacion_id].append(event)

    elaboracion_min: list[float] = []
    respuesta_h: list[float] = []
    espera_h: list[float] = []
    creadas = emitidas = dentro_sla_respuesta = con_aprobacion = 0
    resueltas = resueltas_en_sla = 0
    reemplazadas = con_seguimiento = 0
    cierres = {T.COTIZACION_GANADA: 0, T.COTIZACION_PERDIDA: 0, T.COTIZACION_VENCIDA: 0}

    for quote_events in by_quote.values():
        tipos = {e.tipo for e in quote_events}
        creada = next((e for e in quote_events if e.tipo in CREATION), None)
        emitida = next((e for e in quote_events if e.tipo is T.COTIZACION_EMITIDA), None)
        creadas += creada is not None
        con_aprobacion += T.APROBACION_SOLICITADA in tipos

        # Tiempo que la cotización pasó esperando aprobación, y espera de cada solicitud.
        en_aprobacion = timedelta(0)
        solicitada_en: datetime | None = None
        for event in quote_events:
            if event.tipo is T.APROBACION_SOLICITADA:
                solicitada_en = event.ocurrido_en
            elif event.tipo in RESOLUTION and solicitada_en is not None:
                espera = business_time_between(solicitada_en, event.ocurrido_en, calendar)
                en_aprobacion += espera
                espera_h.append(espera.total_seconds() / 3600)
                resueltas += 1
                resueltas_en_sla += bool(event.payload.get("dentro_del_sla"))
                solicitada_en = None

        for tipo in cierres:
            cierres[tipo] += tipo in tipos

        if emitida is None:
            continue
        emitidas += 1
        reemplazadas += T.COTIZACION_REEMPLAZADA in tipos
        con_seguimiento += bool(tipos & FOLLOW_UP_EVIDENCE)

        if creada is not None:
            trabajo = business_time_between(creada.ocurrido_en, emitida.ocurrido_en, calendar) - en_aprobacion
            elaboracion_min.append(max(trabajo.total_seconds(), 0) / 60)

        recibida = emitida.payload.get("recibida_en")
        if recibida:
            respuesta = business_time_between(datetime.fromisoformat(recibida), emitida.ocurrido_en, calendar)
            respuesta_h.append(respuesta.total_seconds() / 3600)
            dentro_sla_respuesta += respuesta <= timedelta(minutes=sla_respuesta_minutos)

    cerradas = sum(cierres.values())
    sla_h = sla_respuesta_minutos / 60
    indicadores = [
        Kpi("K2", "Tiempo de elaboración", _average(elaboracion_min), "min", 24.0, 7.0, "menor", len(elaboracion_min),
            "Promedio de (emisión − creación − tiempo en aprobación)"),
        Kpi("K3", "Tiempo de respuesta al canal", _average(respuesta_h), "h", 6.4, 1.5, "menor", len(respuesta_h),
            "Promedio de (emisión − recepción), en horas hábiles"),
        Kpi("K4", f"Cumplimiento del SLA de respuesta ({sla_h:g} h)", _percentage(dentro_sla_respuesta, len(respuesta_h)),
            "%", 58.0, 92.0, "mayor", len(respuesta_h), f"Cotizaciones respondidas en ≤ {sla_h:g} h ÷ emitidas"),
        Kpi("K11", "Espera por aprobación", _average(espera_h), "h", 5.2, 1.0, "menor", len(espera_h),
            "Promedio de (resolución − solicitud), en horas hábiles"),
        Kpi("K11b", "Aprobaciones dentro del SLA", _percentage(resueltas_en_sla, resueltas), "%", None, 90.0, "mayor",
            resueltas, "Solicitudes resueltas dentro del SLA ÷ solicitudes resueltas"),
        Kpi("K8", "Retrabajo", _percentage(reemplazadas, emitidas), "%", 12.0, 4.0, "menor", emitidas,
            "Cotizaciones con nueva versión tras la emisión ÷ emitidas"),
        Kpi("K13", "Conversión", _percentage(cierres[T.COTIZACION_GANADA], cerradas), "%", 31.0, 36.0, "mayor", cerradas,
            "Ganadas ÷ (ganadas + perdidas + vencidas)"),
        Kpi("K14", "Cotizaciones con seguimiento", _percentage(con_seguimiento, emitidas), "%", 54.0, 100.0, "mayor",
            emitidas, "Emitidas con seguimiento programado, tarea o cierre ÷ emitidas"),
        Kpi("K10", "Cotizaciones que requieren aprobación", _percentage(con_aprobacion, creadas), "%", 22.0, None, "menor",
            creadas, "Cotizaciones con solicitud de aprobación ÷ creadas"),
    ]
    totales = {
        "creadas": creadas,
        "emitidas": emitidas,
        "aprobaciones_resueltas": resueltas,
        "ganadas": cierres[T.COTIZACION_GANADA],
        "perdidas": cierres[T.COTIZACION_PERDIDA],
        "vencidas": cierres[T.COTIZACION_VENCIDA],
        "reemplazadas": reemplazadas,
    }
    return KpiReport(totales, indicadores)
