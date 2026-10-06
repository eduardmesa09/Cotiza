"""Solicitud de aprobación, tarea de seguimiento y el ciclo posterior a la emisión, en el dominio."""

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.approval import ApprovalRequest, ApprovalStatus, CommentRequiredError
from app.domain.errors import InvalidTransitionError, PermissionDeniedError
from app.domain.followup import FollowUpTask, TaskOutcome, TaskStatus
from app.domain.parties import Actor, Role
from app.domain.pricing_engine import Evaluation
from app.domain.quote import Quote, QuoteLine
from app.domain.state_machine import QuoteState

NOW = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
EJECUTIVO = Actor(1, Role.EJECUTIVO)
APROBADOR = Actor(2, Role.APROBADOR)
GERENTE = Actor(3, Role.GERENTE)


def solicitud() -> ApprovalRequest:
    return ApprovalRequest(cotizacion_id=10, solicitante_id=EJECUTIVO.id, solicitada_en=NOW, vence_en=NOW + timedelta(hours=1))


def quote(estado: QuoteState, **kwargs) -> Quote:
    q = Quote(canal_id=1, ejecutivo_id=EJECUTIVO.id, recibida_en=NOW, creada_en=NOW, id=10, numero="COT-000010")
    q.lineas = [QuoteLine("POR-1", 20, cantidad_comprometida=20)]
    q.estado = estado
    for name, value in kwargs.items():
        setattr(q, name, value)
    return q


# --- Solicitud de aprobación ----------------------------------------------------------


@pytest.mark.parametrize("actor", [APROBADOR, GERENTE])
@pytest.mark.parametrize("aprobar, estado", [(True, ApprovalStatus.APROBADA), (False, ApprovalStatus.RECHAZADA)])
def test_aprobador_y_gerente_resuelven_con_comentario(actor, aprobar, estado):
    s = solicitud()
    s.resolver(aprobar, actor, "  Revisado con el canal  ", NOW + timedelta(minutes=10))
    assert s.estado is estado
    assert s.resuelta_por_id == actor.id
    assert s.comentario == "Revisado con el canal"
    assert s.resuelta_dentro_del_sla()


@pytest.mark.parametrize("comentario", ["", "   ", None])
def test_el_comentario_es_obligatorio(comentario):
    s = solicitud()
    with pytest.raises(CommentRequiredError):
        s.resolver(True, APROBADOR, comentario, NOW)
    assert s.pendiente


def test_segregacion_de_funciones_quien_propone_no_aprueba():
    """Aunque el proponente tuviera rol de aprobador, no puede resolver su propia solicitud."""
    s = solicitud()
    proponente_con_rol_aprobador = Actor(EJECUTIVO.id, Role.APROBADOR)
    with pytest.raises(PermissionDeniedError, match="propone"):
        s.resolver(True, proponente_con_rol_aprobador, "me apruebo", NOW)
    assert s.pendiente


@pytest.mark.parametrize("rol", [Role.EJECUTIVO, Role.PRICING, Role.ADMIN])
def test_otros_roles_no_resuelven(rol):
    with pytest.raises(PermissionDeniedError):
        solicitud().resolver(True, Actor(99, rol), "ok", NOW)


def test_no_se_resuelve_dos_veces():
    s = solicitud()
    s.resolver(False, APROBADOR, "no", NOW)
    with pytest.raises(InvalidTransitionError):
        s.resolver(True, GERENTE, "sí", NOW)
    assert s.estado is ApprovalStatus.RECHAZADA


def test_rn09_escalar_cuando_vence_el_sla():
    s = solicitud()
    assert not s.debe_escalarse(NOW + timedelta(minutes=59))
    assert s.debe_escalarse(NOW + timedelta(hours=1))
    s.escalar(NOW + timedelta(hours=1))
    assert s.escalada and s.escalada_en == NOW + timedelta(hours=1)
    assert s.pendiente  # escalar no resuelve
    assert not s.debe_escalarse(NOW + timedelta(hours=5))
    with pytest.raises(InvalidTransitionError):
        s.escalar(NOW + timedelta(hours=6))


def test_resuelta_fuera_del_sla():
    s = solicitud()
    s.resolver(True, GERENTE, "tarde", NOW + timedelta(hours=2))
    assert not s.resuelta_dentro_del_sla()


def test_una_solicitud_resuelta_no_se_escala():
    s = solicitud()
    s.resolver(True, APROBADOR, "ok", NOW)
    assert not s.debe_escalarse(NOW + timedelta(days=1))
    with pytest.raises(InvalidTransitionError):
        s.escalar(NOW + timedelta(days=1))


# --- Cotización: aprobación -----------------------------------------------------------


def test_aprobar_no_cambia_el_estado_y_habilita_la_emision():
    q = quote(QuoteState.PENDIENTE_APROBACION, evaluacion=Evaluation.REQUIERE_APROBACION)
    q.aprobar()
    assert q.estado is QuoteState.PENDIENTE_APROBACION and q.aprobada
    with pytest.raises(InvalidTransitionError):
        q.rechazar()


def test_rechazar_devuelve_a_calculada():
    q = quote(QuoteState.PENDIENTE_APROBACION, evaluacion=Evaluation.REQUIERE_APROBACION)
    q.rechazar()
    assert q.estado is QuoteState.CALCULADA and not q.aprobada


# --- Cotización: seguimiento, cierre y vigencia ---------------------------------------


def test_iniciar_seguimiento_y_cerrar():
    q = quote(QuoteState.EMITIDA, proximo_seguimiento_en=NOW)
    q.iniciar_seguimiento()
    assert q.estado is QuoteState.EN_SEGUIMIENTO and q.proximo_seguimiento_en is None
    q.mantener_en_seguimiento(NOW + timedelta(hours=48))
    assert q.proximo_seguimiento_en == NOW + timedelta(hours=48)
    q.perder(NOW + timedelta(hours=50))
    assert q.estado is QuoteState.PERDIDA
    assert q.cerrada_en == NOW + timedelta(hours=50) and q.proximo_seguimiento_en is None


def test_mantener_en_seguimiento_exige_estar_en_seguimiento():
    with pytest.raises(InvalidTransitionError):
        quote(QuoteState.EMITIDA).mantener_en_seguimiento(NOW)


@pytest.mark.parametrize("estado", [QuoteState.EMITIDA, QuoteState.EN_SEGUIMIENTO])
def test_rn12_vencer_desde_emitida_o_en_seguimiento(estado):
    q = quote(estado)
    q.vencer(NOW)
    assert q.estado is QuoteState.VENCIDA and q.cerrada_en == NOW


@pytest.mark.parametrize("estado", [QuoteState.BORRADOR, QuoteState.CALCULADA, QuoteState.PENDIENTE_APROBACION, QuoteState.GANADA])
def test_no_vence_lo_que_no_esta_emitido_o_ya_cerro(estado):
    with pytest.raises(InvalidTransitionError):
        quote(estado).vencer(NOW)


# --- Cotización: versiones (RN-13) ----------------------------------------------------


@pytest.mark.parametrize("estado", [QuoteState.EMITIDA, QuoteState.EN_SEGUIMIENTO])
def test_rn13_nueva_version_reemplaza_a_la_anterior(estado):
    v1 = quote(estado, proximo_seguimiento_en=NOW, total=1)
    v2 = v1.nueva_version(NOW + timedelta(hours=1))

    assert v1.reemplazada and v1.estado is estado  # conserva estado y precios
    assert v1.proximo_seguimiento_en is None
    assert v1.acciones_permitidas == frozenset() and not v1.puede_versionarse

    assert (v2.numero, v2.version, v2.version_anterior_id) == ("COT-000010", 2, 10)
    assert v2.id is None and v2.estado is QuoteState.BORRADOR
    assert v2.total is None and v2.evaluacion is None
    assert [(l.referencia, l.cantidad, l.resultado, l.cantidad_comprometida) for l in v2.lineas] == [("POR-1", 20, None, 0)]
    assert v2.creada_en == v2.recibida_en == NOW + timedelta(hours=1)


@pytest.mark.parametrize(
    "estado", [QuoteState.BORRADOR, QuoteState.CALCULADA, QuoteState.PENDIENTE_APROBACION, QuoteState.GANADA, QuoteState.PERDIDA, QuoteState.VENCIDA]
)
def test_rn13_solo_se_versiona_una_cotizacion_emitida_y_vigente(estado):
    with pytest.raises(InvalidTransitionError):
        quote(estado).nueva_version(NOW)


def test_rn13_una_version_reemplazada_no_se_versiona_ni_se_cierra_ni_entra_en_seguimiento():
    v1 = quote(QuoteState.EMITIDA)
    v1.nueva_version(NOW)
    for operacion in (lambda: v1.nueva_version(NOW), lambda: v1.ganar(NOW), lambda: v1.vencer(NOW), v1.iniciar_seguimiento):
        with pytest.raises(InvalidTransitionError):
            operacion()


# --- Tarea de seguimiento -------------------------------------------------------------


def test_cerrar_tarea_de_seguimiento():
    task = FollowUpTask(cotizacion_id=10, ejecutivo_id=1, creada_en=NOW)
    task.cerrar(TaskOutcome.MANTENER, NOW + timedelta(hours=1), "  llamar el viernes ")
    assert task.estado is TaskStatus.CERRADA
    assert (task.resultado, task.nota, task.cerrada_en) == (TaskOutcome.MANTENER, "llamar el viernes", NOW + timedelta(hours=1))
    with pytest.raises(InvalidTransitionError):
        task.cerrar(TaskOutcome.GANADA, NOW)


def test_la_nota_vacia_se_guarda_como_nula():
    task = FollowUpTask(cotizacion_id=10, ejecutivo_id=1, creada_en=NOW)
    task.cerrar(TaskOutcome.GANADA, NOW, "   ")
    assert task.nota is None
