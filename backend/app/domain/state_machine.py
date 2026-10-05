"""Máquina de estados de la cotización (Figura 8 del informe). Módulo puro.

Toda transición pasa por `next_state`; lo que no esté aquí no es posible y falla con
InvalidTransitionError. Así una cotización pendiente no se emite sin resolución explícita
y una emitida no se modifica: solo se cierra o se reemplaza por una nueva versión (RN-13).
"""

from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import InvalidTransitionError
from app.domain.pricing_engine import Evaluation


class QuoteState(StrEnum):
    BORRADOR = "BORRADOR"
    CALCULADA = "CALCULADA"
    PENDIENTE_APROBACION = "PENDIENTE_APROBACION"
    EMITIDA = "EMITIDA"
    EN_SEGUIMIENTO = "EN_SEGUIMIENTO"
    GANADA = "GANADA"
    PERDIDA = "PERDIDA"
    VENCIDA = "VENCIDA"


class Action(StrEnum):
    EDITAR = "EDITAR"
    CALCULAR = "CALCULAR"
    SOLICITAR_APROBACION = "SOLICITAR_APROBACION"
    APROBAR = "APROBAR"
    RECHAZAR = "RECHAZAR"
    ESCALAR = "ESCALAR"
    EMITIR = "EMITIR"
    INICIAR_SEGUIMIENTO = "INICIAR_SEGUIMIENTO"
    GANAR = "GANAR"
    PERDER = "PERDER"
    VENCER = "VENCER"


S, A = QuoteState, Action

FINAL_STATES = frozenset({S.GANADA, S.PERDIDA, S.VENCIDA})

# Estados en los que la cotización compromete inventario si sigue vigente (RN-10).
COMMITTING_STATES = frozenset({S.EMITIDA, S.EN_SEGUIMIENTO})

TRANSITIONS: dict[tuple[QuoteState, Action], QuoteState] = {
    (S.BORRADOR, A.EDITAR): S.BORRADOR,
    (S.BORRADOR, A.CALCULAR): S.CALCULADA,
    (S.CALCULADA, A.EDITAR): S.BORRADOR,
    # Recalcular sin editar refresca precios y disponibilidad antes de emitir.
    (S.CALCULADA, A.CALCULAR): S.CALCULADA,
    (S.CALCULADA, A.SOLICITAR_APROBACION): S.PENDIENTE_APROBACION,
    (S.CALCULADA, A.EMITIR): S.EMITIDA,
    # Aprobar no cambia el estado: la emisión la confirma después el ejecutivo.
    (S.PENDIENTE_APROBACION, A.APROBAR): S.PENDIENTE_APROBACION,
    (S.PENDIENTE_APROBACION, A.ESCALAR): S.PENDIENTE_APROBACION,
    (S.PENDIENTE_APROBACION, A.RECHAZAR): S.CALCULADA,
    (S.PENDIENTE_APROBACION, A.EMITIR): S.EMITIDA,
    (S.EMITIDA, A.INICIAR_SEGUIMIENTO): S.EN_SEGUIMIENTO,
    (S.EMITIDA, A.GANAR): S.GANADA,
    (S.EMITIDA, A.VENCER): S.VENCIDA,
    (S.EN_SEGUIMIENTO, A.GANAR): S.GANADA,
    (S.EN_SEGUIMIENTO, A.PERDER): S.PERDIDA,
    (S.EN_SEGUIMIENTO, A.VENCER): S.VENCIDA,
}


@dataclass(frozen=True)
class TransitionContext:
    """Datos de los que dependen las condiciones de algunas transiciones."""

    evaluacion: Evaluation | None = None
    # La solicitud de aprobación vigente ya fue aprobada.
    aprobada: bool = False


def _guard(estado: QuoteState, accion: Action, ctx: TransitionContext) -> str | None:
    """Devuelve el motivo por el que la transición no procede, o None si procede."""
    if estado is S.CALCULADA and accion is A.SOLICITAR_APROBACION:
        if ctx.evaluacion is Evaluation.NO_EMITIBLE:
            return "la cotización no es emitible: corrija las líneas no cotizables o bajo costo"
        if ctx.evaluacion is not Evaluation.REQUIERE_APROBACION:
            return "la cotización no requiere aprobación"
    if estado is S.CALCULADA and accion is A.EMITIR:
        if ctx.evaluacion is Evaluation.REQUIERE_APROBACION:
            return "el margen está por debajo del mínimo: requiere aprobación"
        if ctx.evaluacion is not Evaluation.LISTA_PARA_EMITIR:
            return "la cotización no es emitible: tiene líneas no cotizables o bajo costo"
    if estado is S.PENDIENTE_APROBACION:
        if accion is A.EMITIR and not ctx.aprobada:
            return "la solicitud de aprobación no ha sido aprobada"
        if accion in (A.APROBAR, A.RECHAZAR, A.ESCALAR) and ctx.aprobada:
            return "la solicitud de aprobación ya fue aprobada"
    return None


def next_state(estado: QuoteState, accion: Action, ctx: TransitionContext = TransitionContext()) -> QuoteState:
    destino = TRANSITIONS.get((estado, accion))
    if destino is None:
        raise InvalidTransitionError(f"No se puede {accion.value} una cotización en estado {estado.value}")
    motivo = _guard(estado, accion, ctx)
    if motivo is not None:
        raise InvalidTransitionError(f"No se puede {accion.value}: {motivo}")
    return destino


def allowed_actions(estado: QuoteState, ctx: TransitionContext = TransitionContext()) -> frozenset[Action]:
    """Acciones posibles ahora mismo. La interfaz las usa para habilitar botones."""
    return frozenset(
        accion for (origen, accion) in TRANSITIONS if origen is estado and _guard(estado, accion, ctx) is None
    )
