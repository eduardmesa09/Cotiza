"""Flujo de aprobación (M4): solicitar, consultar la cola y resolver con comentario obligatorio."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.application.access import load_own_quote, load_quote
from app.domain.approval import RESOLVER_ROLES, ApprovalRequest
from app.domain.business_time import business_time_between
from app.domain.deadlines import approval_due
from app.domain.errors import NotFoundError, PermissionDeniedError
from app.domain.events import EventType
from app.domain.parties import Actor, Role
from app.domain.quote import Quote
from app.ports.external import ClockPort, EventPort, NotificationPort, UserDirectoryPort
from app.ports.repositories import ApprovalRepository, PricingRepository, QuoteRepository


@dataclass(frozen=True)
class QueueItem:
    """Una solicitud con todo el contexto que necesita quien decide."""

    solicitud: ApprovalRequest
    cotizacion: Quote
    # Tiempo hábil que queda antes de que venza el SLA; cero si ya venció.
    sla_restante_segundos: int


class ApprovalService:
    def __init__(
        self,
        quotes: QuoteRepository,
        approvals: ApprovalRepository,
        pricing: PricingRepository,
        events: EventPort,
        notifications: NotificationPort,
        users: UserDirectoryPort,
        clock: ClockPort,
    ) -> None:
        self.quotes = quotes
        self.approvals = approvals
        self.pricing = pricing
        self.events = events
        self.notifications = notifications
        self.users = users
        self.clock = clock

    # --- Solicitar (A4) ----------------------------------------------------------------

    def request(self, actor: Actor, quote_id: int) -> Quote:
        quote = load_own_quote(self.quotes, actor, quote_id)
        ahora = self.clock.now()
        settings = self.pricing.get_settings()

        quote.solicitar_aprobacion()
        self.quotes.save(quote)
        solicitud = self.approvals.add(
            ApprovalRequest(
                cotizacion_id=quote.id,
                solicitante_id=actor.id,
                solicitada_en=ahora,
                vence_en=approval_due(ahora, settings.sla_aprobacion_minutos, settings.calendar),
            )
        )
        self.events.record(
            EventType.APROBACION_SOLICITADA,
            ahora,
            quote.id,
            actor.id,
            {
                "estado_anterior": "CALCULADA",
                "estado_nuevo": quote.estado,
                "solicitud_id": solicitud.id,
                "vence_en": solicitud.vence_en.isoformat(),
                "total": str(quote.total),
                "lineas_bajo_margen": [
                    {
                        "referencia": l.referencia,
                        "descuento_adicional": str(l.descuento_adicional),
                        "margen": str(l.resultado.margen),
                        "margen_minimo": str(l.resultado.margen_minimo),
                    }
                    for l in quote.lineas
                    if l.resultado is not None and l.resultado.requiere_aprobacion
                ],
            },
        )
        for aprobador_id in self.users.ids_with_role(Role.APROBADOR):
            self.notifications.notify(
                aprobador_id,
                "APROBACION_SOLICITADA",
                f"La cotización {quote.numero} requiere su aprobación (total USD {quote.total}).",
                ahora,
                quote.id,
            )
        return quote

    # --- Cola --------------------------------------------------------------------------

    def queue(self, actor: Actor) -> Sequence[QueueItem]:
        """Solicitudes pendientes, por antigüedad y monto. El gerente recibe las escaladas."""
        if actor.rol not in RESOLVER_ROLES:
            raise PermissionDeniedError("Solo un aprobador o el gerente comercial consultan la cola de aprobaciones")
        ahora = self.clock.now()
        calendar = self.pricing.get_settings().calendar
        items = []
        for solicitud in self.approvals.list_pending(solo_escaladas=actor.rol is Role.GERENTE):
            quote = load_quote(self.quotes, solicitud.cotizacion_id)
            restante = business_time_between(ahora, solicitud.vence_en, calendar)
            items.append(QueueItem(solicitud, quote, int(restante.total_seconds())))
        items.sort(key=lambda i: (i.solicitud.solicitada_en, -(i.cotizacion.total or 0)))
        return items

    def latest_for_quote(self, quote_id: int) -> ApprovalRequest | None:
        return self.approvals.latest_for_quote(quote_id)

    # --- Resolver ----------------------------------------------------------------------

    def resolve(self, actor: Actor, request_id: int, aprobar: bool, comentario: str) -> Quote:
        solicitud = self.approvals.get(request_id)
        if solicitud is None:
            raise NotFoundError(f"La solicitud de aprobación {request_id} no existe")
        quote = load_quote(self.quotes, solicitud.cotizacion_id)
        ahora = self.clock.now()
        calendar = self.pricing.get_settings().calendar

        # Valida rol, segregación de funciones, estado y comentario antes de tocar la cotización.
        solicitud.resolver(aprobar, actor, comentario, ahora)
        anterior = quote.estado
        if aprobar:
            quote.aprobar()
        else:
            quote.rechazar()
        self.approvals.save(solicitud)
        self.quotes.save(quote)

        espera = business_time_between(solicitud.solicitada_en, ahora, calendar)
        self.events.record(
            EventType.APROBACION_APROBADA if aprobar else EventType.APROBACION_RECHAZADA,
            ahora,
            quote.id,
            actor.id,
            {
                "estado_anterior": anterior,
                "estado_nuevo": quote.estado,
                "solicitud_id": solicitud.id,
                "comentario": solicitud.comentario,
                "solicitada_en": solicitud.solicitada_en.isoformat(),
                "espera_segundos": int(espera.total_seconds()),
                "dentro_del_sla": solicitud.resuelta_dentro_del_sla(),
                "escalada": solicitud.escalada,
            },
        )
        self.notifications.notify(
            solicitud.solicitante_id,
            "APROBACION_APROBADA" if aprobar else "APROBACION_RECHAZADA",
            (
                f"La cotización {quote.numero} fue aprobada: ya puede confirmar la emisión."
                if aprobar
                else f"La cotización {quote.numero} fue rechazada: ajuste el descuento. Motivo: {solicitud.comentario}"
            ),
            ahora,
            quote.id,
        )
        return quote

    # --- Escalamiento (A5) -------------------------------------------------------------

    def escalate_overdue(self, ahora: datetime) -> int:
        """RN-09: escala al gerente las solicitudes con el SLA vencido. Lo invoca el planificador."""
        gerentes = self.users.ids_with_role(Role.GERENTE)
        aprobadores = self.users.ids_with_role(Role.APROBADOR)
        escaladas = 0
        for solicitud in self.approvals.list_overdue(ahora):
            quote = load_quote(self.quotes, solicitud.cotizacion_id)
            quote.escalar()
            solicitud.escalar(ahora)
            self.approvals.save(solicitud)
            self.events.record(
                EventType.APROBACION_ESCALADA,
                ahora,
                quote.id,
                None,
                {"solicitud_id": solicitud.id, "vencio_en": solicitud.vence_en.isoformat()},
            )
            for gerente_id in gerentes:
                self.notifications.notify(
                    gerente_id,
                    "APROBACION_ESCALADA",
                    f"La aprobación de la cotización {quote.numero} venció su SLA y fue escalada a usted.",
                    ahora,
                    quote.id,
                )
            for aprobador_id in aprobadores:
                self.notifications.notify(
                    aprobador_id,
                    "APROBACION_ESCALADA",
                    f"La aprobación de la cotización {quote.numero} venció su SLA y fue escalada a la gerencia comercial.",
                    ahora,
                    quote.id,
                )
            escaladas += 1
        return escaladas
