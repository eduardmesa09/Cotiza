"""Máquina de estados de la cotización (Figura 8), incluidas todas las transiciones inválidas."""

from itertools import product

import pytest

from app.domain.errors import InvalidTransitionError
from app.domain.pricing_engine import Evaluation
from app.domain.state_machine import (
    COMMITTING_STATES,
    FINAL_STATES,
    TRANSITIONS,
    Action,
    QuoteState,
    TransitionContext,
    allowed_actions,
    next_state,
)

S, A = QuoteState, Action

LISTA = TransitionContext(evaluacion=Evaluation.LISTA_PARA_EMITIR)
REQUIERE = TransitionContext(evaluacion=Evaluation.REQUIERE_APROBACION)
NO_EMITIBLE = TransitionContext(evaluacion=Evaluation.NO_EMITIBLE)
APROBADA = TransitionContext(evaluacion=Evaluation.REQUIERE_APROBACION, aprobada=True)

# Las transiciones de la Figura 8, escritas aquí de forma independiente del código:
# (estado origen, acción, contexto que la permite, estado destino).
VALIDAS = [
    (S.BORRADOR, A.EDITAR, TransitionContext(), S.BORRADOR),
    (S.BORRADOR, A.CALCULAR, TransitionContext(), S.CALCULADA),
    (S.CALCULADA, A.EDITAR, LISTA, S.BORRADOR),
    (S.CALCULADA, A.CALCULAR, LISTA, S.CALCULADA),
    (S.CALCULADA, A.SOLICITAR_APROBACION, REQUIERE, S.PENDIENTE_APROBACION),
    (S.CALCULADA, A.EMITIR, LISTA, S.EMITIDA),
    (S.PENDIENTE_APROBACION, A.APROBAR, REQUIERE, S.PENDIENTE_APROBACION),
    (S.PENDIENTE_APROBACION, A.ESCALAR, REQUIERE, S.PENDIENTE_APROBACION),
    (S.PENDIENTE_APROBACION, A.RECHAZAR, REQUIERE, S.CALCULADA),
    (S.PENDIENTE_APROBACION, A.EMITIR, APROBADA, S.EMITIDA),
    (S.EMITIDA, A.INICIAR_SEGUIMIENTO, TransitionContext(), S.EN_SEGUIMIENTO),
    (S.EMITIDA, A.GANAR, TransitionContext(), S.GANADA),
    (S.EMITIDA, A.VENCER, TransitionContext(), S.VENCIDA),
    (S.EN_SEGUIMIENTO, A.GANAR, TransitionContext(), S.GANADA),
    (S.EN_SEGUIMIENTO, A.PERDER, TransitionContext(), S.PERDIDA),
    (S.EN_SEGUIMIENTO, A.VENCER, TransitionContext(), S.VENCIDA),
]

PARES_VALIDOS = {(origen, accion) for origen, accion, _, _ in VALIDAS}
PARES_INVALIDOS = [par for par in product(S, A) if par not in PARES_VALIDOS]
CONTEXTOS = [TransitionContext(), LISTA, REQUIERE, NO_EMITIBLE, APROBADA]


@pytest.mark.parametrize("origen, accion, ctx, destino", VALIDAS)
def test_transicion_valida(origen, accion, ctx, destino):
    assert next_state(origen, accion, ctx) is destino


def test_la_tabla_del_codigo_no_tiene_transiciones_de_mas():
    assert set(TRANSITIONS) == PARES_VALIDOS


@pytest.mark.parametrize("origen, accion", PARES_INVALIDOS)
def test_transicion_invalida_falla_con_error_de_dominio_en_cualquier_contexto(origen, accion):
    for ctx in CONTEXTOS:
        with pytest.raises(InvalidTransitionError):
            next_state(origen, accion, ctx)


def test_hay_72_combinaciones_invalidas_cubiertas():
    assert len(PARES_INVALIDOS) == len(S) * len(A) - len(VALIDAS) == 72


# --- Condiciones (guardas) -------------------------------------------------------------


def test_rn07_no_se_emite_si_requiere_aprobacion():
    with pytest.raises(InvalidTransitionError, match="requiere aprobación"):
        next_state(S.CALCULADA, A.EMITIR, REQUIERE)


def test_rn08_no_se_emite_con_lineas_no_cotizables_o_bajo_costo():
    with pytest.raises(InvalidTransitionError, match="no es emitible"):
        next_state(S.CALCULADA, A.EMITIR, NO_EMITIBLE)


def test_no_se_emite_sin_haber_calculado():
    with pytest.raises(InvalidTransitionError):
        next_state(S.CALCULADA, A.EMITIR, TransitionContext())
    with pytest.raises(InvalidTransitionError):
        next_state(S.BORRADOR, A.EMITIR, LISTA)


def test_e5_no_se_puede_solicitar_aprobacion_de_una_cotizacion_no_emitible():
    with pytest.raises(InvalidTransitionError, match="corrija"):
        next_state(S.CALCULADA, A.SOLICITAR_APROBACION, NO_EMITIBLE)


def test_no_se_solicita_aprobacion_si_no_hace_falta():
    with pytest.raises(InvalidTransitionError, match="no requiere aprobación"):
        next_state(S.CALCULADA, A.SOLICITAR_APROBACION, LISTA)


def test_pendiente_no_se_emite_sin_aprobacion_explicita():
    with pytest.raises(InvalidTransitionError, match="no ha sido aprobada"):
        next_state(S.PENDIENTE_APROBACION, A.EMITIR, REQUIERE)


@pytest.mark.parametrize("accion", [A.APROBAR, A.RECHAZAR, A.ESCALAR])
def test_una_solicitud_ya_aprobada_no_se_vuelve_a_resolver_ni_a_escalar(accion):
    with pytest.raises(InvalidTransitionError, match="ya fue aprobada"):
        next_state(S.PENDIENTE_APROBACION, accion, APROBADA)


def test_pendiente_no_se_puede_editar_ni_recalcular():
    for accion in (A.EDITAR, A.CALCULAR):
        with pytest.raises(InvalidTransitionError):
            next_state(S.PENDIENTE_APROBACION, accion, REQUIERE)


def test_perdida_solo_se_registra_desde_seguimiento():
    with pytest.raises(InvalidTransitionError):
        next_state(S.EMITIDA, A.PERDER)


# --- RN-13 y estados finales -----------------------------------------------------------


@pytest.mark.parametrize("estado", [S.EMITIDA, S.EN_SEGUIMIENTO])
@pytest.mark.parametrize("accion", [A.EDITAR, A.CALCULAR, A.EMITIR])
def test_rn13_una_cotizacion_emitida_no_se_modifica_ni_se_recalcula(estado, accion):
    with pytest.raises(InvalidTransitionError):
        next_state(estado, accion, LISTA)


@pytest.mark.parametrize("estado", sorted(FINAL_STATES))
def test_los_estados_finales_no_tienen_salida(estado):
    assert allowed_actions(estado, LISTA) == frozenset()
    for accion in A:
        with pytest.raises(InvalidTransitionError):
            next_state(estado, accion, LISTA)


def test_estados_finales_y_estados_que_comprometen_inventario():
    assert FINAL_STATES == {S.GANADA, S.PERDIDA, S.VENCIDA}
    assert COMMITTING_STATES == {S.EMITIDA, S.EN_SEGUIMIENTO}


# --- Acciones permitidas ---------------------------------------------------------------


def test_acciones_permitidas_dependen_de_la_evaluacion():
    assert allowed_actions(S.CALCULADA, LISTA) == {A.EDITAR, A.CALCULAR, A.EMITIR}
    assert allowed_actions(S.CALCULADA, REQUIERE) == {A.EDITAR, A.CALCULAR, A.SOLICITAR_APROBACION}
    assert allowed_actions(S.CALCULADA, NO_EMITIBLE) == {A.EDITAR, A.CALCULAR}


def test_acciones_permitidas_en_pendiente_dependen_de_la_aprobacion():
    assert allowed_actions(S.PENDIENTE_APROBACION, REQUIERE) == {A.APROBAR, A.RECHAZAR, A.ESCALAR}
    assert allowed_actions(S.PENDIENTE_APROBACION, APROBADA) == {A.EMITIR}


def test_el_mensaje_de_error_nombra_la_accion_y_el_estado():
    with pytest.raises(InvalidTransitionError, match="EMITIR una cotización en estado GANADA"):
        next_state(S.GANADA, A.EMITIR)
