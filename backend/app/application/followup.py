"""Seguimiento, cierre, vigencia y versiones (M6): lo que pasa después de emitir."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.application.access import load_own_quote, load_quote, require_executive
from app.domain.deadlines import follow_up_due
from app.domain.errors import InvalidTransitionError, NotFoundError, PermissionDeniedError
from app.domain.events import EventType
from app.domain.followup import FollowUpTask, TaskOutcome
from app.domain.parties import Actor
from app.domain.quote import Quote
from app.domain.state_machine import QuoteState
from app.ports.external import ClockPort, EventPort, NotificationPort
from app.ports.repositories import FollowUpRepository, PricingRepository, QuoteRepository


@dataclass(frozen=True)
class TaskItem:
    tarea: FollowUpTask
    cotizacion: Quote


class FollowUpService:
    def __init__(
        self,
        quotes: QuoteRepository,
        tasks: FollowUpRepository,
        pricing: PricingRepository,
        events: EventPort,
        notifications: NotificationPort,
        clock: ClockPort,
    ) -> None:
        self.quotes = quotes
        self.tasks = tasks
        self.pricing = pricing
        self.events = events
        self.notifications = notifications
        self.clock = clock

    def _close_pending_tasks(self, quote_id: int, resultado: TaskOutcome, ahora: datetime, nota: str | None = None) -> None:
        for task in self.tasks.pending_for_quote(quote_id):
            task.cerrar(resultado, ahora, nota)
            self.tasks.save(task)

    # --- Acciones del ejecutivo --------------------------------------------------------

    def pending_tasks(self, actor: Actor) -> Sequence[TaskItem]:
        require_executive(actor)
        return [
            TaskItem(task, load_quote(self.quotes, task.cotizacion_id))
            for task in self.tasks.list_pending(ejecutivo_id=actor.id)
        ]

    def close(self, actor: Actor, quote_id: int, resultado: TaskOutcome, nota: str | None = None) -> Quote:
        """Cierra la cotización como ganada (orden recibida) o perdida (el canal declina)."""
        quote = load_own_quote(self.quotes, actor, quote_id)
        ahora = self.clock.now()
        anterior = quote.estado
        if resultado is TaskOutcome.GANADA:
            quote.ganar(ahora)
            tipo = EventType.COTIZACION_GANADA
        elif resultado is TaskOutcome.PERDIDA:
            quote.perder(ahora)
            tipo = EventType.COTIZACION_PERDIDA
        else:
            raise InvalidTransitionError("Una cotización solo se cierra como ganada o perdida")
        self.quotes.save(quote)
        self._close_pending_tasks(quote.id, resultado, ahora, nota)
        self.events.record(
            tipo,
            ahora,
            quote.id,
            actor.id,
            {
                "estado_anterior": anterior,
                "estado_nuevo": quote.estado,
                "nota": (nota or "").strip() or None,
                "inventario_liberado": {l.referencia: l.cantidad_comprometida for l in quote.lineas},
            },
        )
        return quote

    def keep_following(self, actor: Actor, quote_id: int, nota: str | None = None) -> Quote:
        """Cierra la tarea actual y programa un nuevo recordatorio con el mismo plazo."""
        quote = load_own_quote(self.quotes, actor, quote_id)
        ahora = self.clock.now()
        if not self.tasks.pending_for_quote(quote.id):
            raise InvalidTransitionError("La cotización no tiene una tarea de seguimiento pendiente")
        proximo = follow_up_due(ahora, self.pricing.get_settings().seguimiento_minutos)
        quote.mantener_en_seguimiento(proximo)
        self.quotes.save(quote)
        self._close_pending_tasks(quote.id, TaskOutcome.MANTENER, ahora, nota)
        self.events.record(
            EventType.SEGUIMIENTO_MANTENIDO,
            ahora,
            quote.id,
            actor.id,
            {"nota": (nota or "").strip() or None, "programado_para": proximo.isoformat()},
        )
        return quote

    def resolve_task(self, actor: Actor, task_id: int, resultado: TaskOutcome, nota: str | None = None) -> Quote:
        task = self.tasks.get(task_id)
        if task is None:
            raise NotFoundError(f"La tarea de seguimiento {task_id} no existe")
        if task.ejecutivo_id != actor.id:
            raise PermissionDeniedError("Solo puede atender sus propias tareas de seguimiento")
        if resultado is TaskOutcome.MANTENER:
            return self.keep_following(actor, task.cotizacion_id, nota)
        return self.close(actor, task.cotizacion_id, resultado, nota)

    # --- Nueva versión (RN-13) ---------------------------------------------------------

    def new_version(self, actor: Actor, quote_id: int) -> Quote:
        anterior = load_own_quote(self.quotes, actor, quote_id)
        ahora = self.clock.now()
        nueva = anterior.nueva_version(ahora)
        self.quotes.save(anterior)
        nueva = self.quotes.add(nueva)
        self._close_pending_tasks(anterior.id, TaskOutcome.REEMPLAZADA, ahora)
        self.events.record(
            EventType.COTIZACION_REEMPLAZADA,
            ahora,
            anterior.id,
            actor.id,
            {
                "reemplazada_por": nueva.id,
                "version_nueva": nueva.version,
                "inventario_liberado": {l.referencia: l.cantidad_comprometida for l in anterior.lineas},
            },
        )
        self.events.record(
            EventType.NUEVA_VERSION_CREADA,
            ahora,
            nueva.id,
            actor.id,
            {"numero": nueva.numero, "version": nueva.version, "version_anterior_id": anterior.id},
        )
        return nueva

    # --- Temporizadores (A7): los invoca el planificador --------------------------------

    def expire_due(self, ahora: datetime) -> int:
        """RN-12: al vencer la vigencia sin orden, la cotización pasa a VENCIDA y libera inventario."""
        vencidas = 0
        for quote in self.quotes.list_expired(ahora):
            anterior = quote.estado
            quote.vencer(ahora)
            self.quotes.save(quote)
            self._close_pending_tasks(quote.id, TaskOutcome.VENCIDA, ahora)
            self.events.record(
                EventType.COTIZACION_VENCIDA,
                ahora,
                quote.id,
                None,
                {
                    "estado_anterior": anterior,
                    "estado_nuevo": quote.estado,
                    "vigente_hasta": quote.vigente_hasta.isoformat(),
                    "inventario_liberado": {l.referencia: l.cantidad_comprometida for l in quote.lineas},
                },
            )
            self.notifications.notify(
                quote.ejecutivo_id,
                "COTIZACION_VENCIDA",
                f"La cotización {quote.numero} venció sin orden de compra; su inventario quedó liberado.",
                ahora,
                quote.id,
            )
            vencidas += 1
        return vencidas

    def start_due_follow_ups(self, ahora: datetime) -> int:
        """RN-12: a las 48 h de emitida sin cierre, crea la tarea de seguimiento para el ejecutivo."""
        creadas = 0
        for quote in self.quotes.list_due_follow_up(ahora):
            recordatorio = quote.estado is QuoteState.EN_SEGUIMIENTO
            if recordatorio:
                # Venía de "mantener en seguimiento": solo se crea el nuevo recordatorio.
                quote.proximo_seguimiento_en = None
            else:
                quote.iniciar_seguimiento()
            self.quotes.save(quote)
            task = self.tasks.add(FollowUpTask(cotizacion_id=quote.id, ejecutivo_id=quote.ejecutivo_id, creada_en=ahora))
            self.events.record(
                EventType.SEGUIMIENTO_INICIADO,
                ahora,
                quote.id,
                None,
                {"estado_nuevo": quote.estado, "tarea_id": task.id, "recordatorio": recordatorio},
            )
            self.notifications.notify(
                quote.ejecutivo_id,
                "SEGUIMIENTO",
                f"La cotización {quote.numero} lleva sin respuesta del canal: tiene una tarea de seguimiento.",
                ahora,
                quote.id,
            )
            creadas += 1
        return creadas
