"""Escenario de demo: precarga unas tres semanas de operación para que el tablero tenga datos.

No inserta filas a mano. Recrea el pasado ejecutando los mismos casos de uso que la
aplicación (crear, calcular, aprobar, emitir, seguir, cerrar) con un reloj que avanza por el
calendario, de modo que los eventos, los PDF y los indicadores son los que produciría el uso
real. Los tiempos simulados apuntan a las metas del capítulo 5 (unos 7 min de elaboración,
1,5 h de respuesta), con casos fuera de plazo para que los indicadores no salgan perfectos.

Uso:  docker compose exec api python -m app.infra.demo
Solo corre sobre una base sin cotizaciones; para repetirlo: docker compose down -v.
"""

import heapq
import random
from collections import Counter
from collections.abc import Iterator
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.adapters.clock import SettableClock
from app.adapters.sql_misc import SqlCustomerAdapter
from app.adapters.sql_repositories import SqlApprovalRepository, SqlPricingRepository
from app.domain.business_time import add_business_time
from app.domain.errors import DomainError
from app.domain.followup import TaskOutcome
from app.domain.kpis import KpiReport
from app.domain.parties import Actor, Role
from app.domain.pricing_engine import Evaluation
from app.domain.quote import Quote, QuoteLine
from app.infra.container import (
    build_approval_service,
    build_deadline_service,
    build_followup_service,
    build_kpi_service,
    build_quote_service,
)
from app.infra.models import Cotizacion, Notificacion, Usuario
from app.infra.security import hash_password
from app.infra.seeds import DEFAULT_PASSWORD
from app.ports.external import CatalogPort, DocumentPort, InventoryPort, StoragePort

SEED = 2026
DAYS_BACK = 21

# Un segundo ejecutivo: así el tablero "propio" de cada uno difiere del general.
SECOND_EXECUTIVE = ("ejecutivo2", "Julián Mora")

APPROVAL_COMMENTS = ["Cliente estratégico, se autoriza", "Autorizado por volumen del trimestre", "Se aprueba para igualar oferta de la competencia"]
REJECTION_COMMENTS = ["El descuento excede lo razonable para esta cuenta", "Margen insuficiente; ofrecer máximo la mitad"]
WON_NOTES = ["Orden de compra recibida", "El canal confirmó la compra"]
LOST_NOTES = ["El canal compró a otro distribuidor", "El proyecto del cliente final se aplazó"]
KEEP_NOTES = ["El canal decide la próxima semana", "Pendiente de aprobación de su cliente final"]


class _Simulation:
    def __init__(
        self,
        session: Session,
        catalog: CatalogPort,
        inventory: InventoryPort,
        documents: DocumentPort,
        storage: StoragePort,
        clock: SettableClock,
    ) -> None:
        self.session = session
        self.clock = clock
        self.quotes = build_quote_service(session, catalog, inventory, clock, documents, storage)
        self.approvals = build_approval_service(session, clock)
        self.followup = build_followup_service(session, clock)
        self.deadlines = build_deadline_service(session, clock)
        self.approval_repo = SqlApprovalRepository(session)
        self.calendar = SqlPricingRepository(session).get_settings().calendar
        self.channels = [c.id for c in SqlCustomerAdapter(session).list()]
        self.skus = sorted(p.referencia for p in catalog.search("", 1000) if p.costo is not None and p.precio_lista is not None)

    def actor(self, usuario: str) -> Actor:
        row = self.session.scalars(select(Usuario).where(Usuario.usuario == usuario)).one()
        return Actor(row.id, Role(row.rol))

    def after(self, moment: datetime, minutes: float) -> datetime:
        """`minutes` de tiempo hábil después: las personas actúan dentro de su jornada."""
        return add_business_time(moment, timedelta(minutes=minutes), self.calendar)

    def random_lines(self, rng: random.Random, with_discount: bool) -> list[QuoteLine]:
        count = rng.choices([1, 2, 3, 4, 6, 8, 10], weights=[20, 22, 20, 14, 10, 8, 6])[0]
        lines = []
        for sku in rng.sample(self.skus, k=min(count, len(self.skus))):
            quantity = rng.choices([rng.randint(1, 9), rng.randint(10, 49), rng.randint(50, 120)], weights=[62, 30, 8])[0]
            lines.append(QuoteLine(sku, quantity))
        if with_discount:
            # El ejecutivo negocia un descuento adicional en la línea principal.
            lines[0].descuento_adicional = Decimal(rng.choice(["0.06", "0.08", "0.10", "0.12"]))
        return lines


def _journey(sim: _Simulation, rng: random.Random, executive: Actor, recibida: datetime) -> Iterator[datetime]:
    """Vida de una cotización. Cada `yield` es el momento en que ocurre el paso siguiente; el
    simulador adelanta el reloj hasta ahí (procesando antes los plazos vencidos) y continúa."""
    approver, manager = sim.actor("aprobador"), sim.actor("gerente")

    # Espera en la cola del ejecutivo: la mayoría se atiende pronto; algunas incumplen las 4 h.
    r = rng.random()
    queue = rng.uniform(8, 85) if r < 0.80 else rng.uniform(90, 200) if r < 0.92 else rng.uniform(250, 400)
    t = sim.after(recibida, queue)
    yield t
    quote = sim.quotes.create(executive, rng.choice(sim.channels), recibida, sim.random_lines(rng, rng.random() < 0.28))

    elaboration = rng.triangular(3.5, 11.5, 6.5)  # minutos de trabajo del ejecutivo
    t = sim.after(t, elaboration * 0.7)
    yield t
    quote = sim.quotes.calculate(executive, quote.id)

    def without_discounts(q: Quote) -> list[QuoteLine]:
        return [QuoteLine(line.referencia, line.cantidad) for line in q.lineas]

    if quote.evaluacion is Evaluation.NO_EMITIBLE:
        # El descuento dejó el precio bajo el costo: el ejecutivo lo retira y recalcula.
        t = sim.after(t, 1.5)
        yield t
        sim.quotes.update(executive, quote.id, quote.canal_id, quote.recibida_en, without_discounts(quote))
        quote = sim.quotes.calculate(executive, quote.id)
        if quote.evaluacion is Evaluation.NO_EMITIBLE:
            return

    if quote.evaluacion is Evaluation.REQUIERE_APROBACION:
        t = sim.after(t, elaboration * 0.2)
        yield t
        sim.approvals.request(executive, quote.id)
        request = sim.approval_repo.latest_for_quote(quote.id)

        # La mayoría se resuelve dentro de la hora; el resto vence, escala y lo resuelve el gerente.
        wait = rng.uniform(6, 50) if rng.random() < 0.90 else rng.uniform(66, 115)
        t = sim.after(t, wait)
        yield t
        approved = rng.random() < 0.82
        comment = rng.choice(APPROVAL_COMMENTS if approved else REJECTION_COMMENTS)
        sim.approvals.resolve(manager if wait > 60 else approver, request.id, approved, comment)

        if approved:
            t = sim.after(t, rng.uniform(1, 4))
            yield t
        else:
            t = sim.after(t, rng.uniform(3, 15))
            yield t
            sim.quotes.update(executive, quote.id, quote.canal_id, quote.recibida_en, without_discounts(quote))
            quote = sim.quotes.calculate(executive, quote.id)
            if quote.evaluacion is not Evaluation.LISTA_PARA_EMITIR:
                return  # queda calculada, a la espera de otra negociación
            t = sim.after(t, 1)
            yield t
    else:
        t = sim.after(t, elaboration * 0.3)
        yield t

    sim.quotes.issue(executive, quote.id)
    emitted = t
    after_follow_up = emitted + timedelta(hours=48, minutes=1)

    outcome = rng.random()
    if outcome < 0.26:  # el canal compra
        yield sim.after(emitted, rng.uniform(60, 1400))
        sim.followup.close(executive, quote.id, TaskOutcome.GANADA, rng.choice(WON_NOTES))
    elif outcome < 0.54:  # el canal declina, tras el seguimiento
        yield sim.after(after_follow_up, rng.uniform(20, 600))
        sim.followup.close(executive, quote.id, TaskOutcome.PERDIDA, rng.choice(LOST_NOTES))
    elif outcome < 0.64:  # se mantiene en seguimiento y luego se define
        t = sim.after(after_follow_up, rng.uniform(20, 300))
        yield t
        sim.followup.keep_following(executive, quote.id, rng.choice(KEEP_NOTES))
        yield sim.after(t + timedelta(hours=48, minutes=1), rng.uniform(20, 300))
        won = rng.random() < 0.5
        sim.followup.close(executive, quote.id, TaskOutcome.GANADA if won else TaskOutcome.PERDIDA, rng.choice(WON_NOTES if won else LOST_NOTES))
    elif outcome < 0.69:  # el canal pide un cambio: nueva versión (retrabajo)
        t = sim.after(emitted, rng.uniform(120, 900))
        yield t
        version = sim.followup.new_version(executive, quote.id)
        t = sim.after(t, rng.uniform(3, 7))
        yield t
        version = sim.quotes.calculate(executive, version.id)
        if version.evaluacion is Evaluation.LISTA_PARA_EMITIR:
            t = sim.after(t, 2)
            yield t
            sim.quotes.issue(executive, version.id)
    # En el resto de los casos nadie responde: vence a los 7 días o sigue abierta.


def _ensure_second_executive(session: Session, now: datetime) -> None:
    usuario, nombre = SECOND_EXECUTIVE
    if session.scalar(select(Usuario).where(Usuario.usuario == usuario)) is None:
        session.add(
            Usuario(
                usuario=usuario,
                nombre=nombre,
                email=f"{usuario}@cotiza.example.com",
                password_hash=hash_password(DEFAULT_PASSWORD),
                rol=Role.EJECUTIVO,
                activo=True,
                creado_en=now,
            )
        )
        session.flush()


def run_demo(
    session: Session,
    catalog: CatalogPort,
    inventory: InventoryPort,
    documents: DocumentPort,
    storage: StoragePort,
    now: datetime,
    seed: int = SEED,
) -> dict:
    """Ejecuta el escenario hasta `now`. Devuelve un resumen: cotizaciones por estado e indicadores."""
    if session.scalar(select(func.count()).select_from(Cotizacion)) > 0:
        raise DomainError("La base ya tiene cotizaciones: el escenario de demo solo corre sobre una base limpia")

    start = now - timedelta(days=DAYS_BACK)
    _ensure_second_executive(session, start)
    clock = SettableClock(start)
    sim = _Simulation(session, catalog, inventory, documents, storage, clock)
    executives = [sim.actor("ejecutivo"), sim.actor(SECOND_EXECUTIVE[0])]
    rng = random.Random(seed)
    tz = sim.calendar.tz

    # Plan: entre 4 y 7 solicitudes por día hábil, recibidas dentro de la jornada.
    pending: list[tuple[datetime, int, Iterator[datetime]]] = []
    day = start.astimezone(tz).date()
    index = 0
    while day <= now.astimezone(tz).date():
        if day.isoweekday() in sim.calendar.dias:
            for _ in range(rng.randint(4, 7)):
                recibida = datetime.combine(day, time(9, 0), tz) + timedelta(minutes=rng.uniform(0, 450))
                journey = _journey(sim, random.Random(seed * 1000 + index), executives[index % 2], recibida)
                first_step = next(journey)
                if recibida < now:
                    heapq.heappush(pending, (first_step, index, journey))
                index += 1
        day += timedelta(days=1)

    # Se ejecutan todos los pasos en orden cronológico, como ocurrieron: el reloj nunca retrocede
    # y antes de cada paso el planificador procesa los plazos vencidos hasta ese momento.
    while pending:
        moment, order, journey = heapq.heappop(pending)
        if moment > now:
            continue  # ese paso todavía no ha ocurrido: la cotización queda como esté
        clock.set(moment.astimezone(timezone.utc))
        sim.deadlines.process()
        try:
            heapq.heappush(pending, (next(journey), order, journey))
        except StopIteration:
            pass
        except DomainError:
            # Por ejemplo, la cotización venció antes de que el ejecutivo alcanzara a cerrarla.
            session.rollback()
        session.commit()

    clock.set(now)
    sim.deadlines.process()
    # Las notificaciones viejas no deben saturar la campana: quedan sin leer solo las del último día.
    session.execute(update(Notificacion).where(Notificacion.creada_en < now - timedelta(days=1)).values(leida=True))
    session.commit()

    states = Counter(session.scalars(select(Cotizacion.estado)))
    report: KpiReport = build_kpi_service(session, clock).dashboard(sim.actor("gerente")).reporte
    return {"cotizaciones": sum(states.values()), "estados": dict(states), "indicadores": report}


def main() -> None:
    # Se importan aquí: son los adaptadores reales, que solo existen dentro del contenedor.
    from app.api.deps import get_catalog, get_documents, get_inventory, get_storage
    from app.infra.db import get_session_factory

    print("Generando el escenario de demo (puede tardar alrededor de un minuto)…")
    with get_session_factory()() as session:
        try:
            summary = run_demo(session, get_catalog(), get_inventory(), get_documents(), get_storage(), datetime.now(timezone.utc))
        except DomainError as exc:
            print(f"No se generó nada: {exc}. Para empezar de cero: docker compose down -v")
            raise SystemExit(1) from exc

    print(f"Listo: {summary['cotizaciones']} cotizaciones.")
    for state, count in sorted(summary["estados"].items()):
        print(f"  {state:<22}{count}")
    print("Indicadores (línea base → medido):")
    for kpi in summary["indicadores"].indicadores:
        print(f"  {kpi.codigo:<5} {kpi.nombre:<46} {kpi.linea_base} → {kpi.valor} {kpi.unidad}")
    print(f"Segundo ejecutivo creado: usuario «{SECOND_EXECUTIVE[0]}», misma contraseña.")


if __name__ == "__main__":
    main()
