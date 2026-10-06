"""Planificador de plazos (A5 y A7): SLA de aprobación, seguimiento a las 48 h y vigencia.

Un único trabajo periódico consulta en la base de datos qué plazos ya se cumplieron. No se
programa un temporizador por cotización: así un reinicio no pierde nada y basta un ciclo
para ponerse al día. Equivale a EventBridge en la arquitectura objetivo.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.adapters.clock import SystemClock
from app.infra.container import build_deadline_service
from app.infra.db import get_session_factory
from app.infra.models import Parametro

# Se usa el logger de uvicorn para que los mensajes salgan en el log del contenedor.
logger = logging.getLogger("uvicorn.error")

DEFAULT_INTERVAL_SECONDS = 30


def run_deadlines() -> None:
    with get_session_factory()() as session:
        try:
            report = build_deadline_service(session, SystemClock()).process()
            session.commit()
        except Exception:
            # Un fallo en un ciclo no debe detener el planificador: se reintenta en el siguiente.
            session.rollback()
            logger.exception("Falló el procesamiento de plazos")
            return
    if report.total:
        logger.info(
            "Plazos procesados: %s vencidas, %s seguimientos, %s escaladas",
            report.vencidas,
            report.seguimientos,
            report.escaladas,
        )


def _interval_seconds() -> int:
    """Se lee al arrancar: cambiar el parámetro requiere reiniciar la API."""
    try:
        with get_session_factory()() as session:
            row = session.get(Parametro, "planificador_intervalo_segundos")
            return max(int(row.valor), 1) if row else DEFAULT_INTERVAL_SECONDS
    except Exception:
        return DEFAULT_INTERVAL_SECONDS


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    interval = _interval_seconds()
    # max_instances=1 y coalesce: nunca dos ciclos a la vez ni ciclos acumulados tras una pausa.
    scheduler.add_job(run_deadlines, "interval", seconds=interval, id="plazos", max_instances=1, coalesce=True)
    scheduler.start()
    logger.info("Planificador de plazos iniciado: cada %s s", interval)
    return scheduler
