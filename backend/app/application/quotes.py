"""Casos de uso de la cotización: crear, editar, calcular, emitir y consultar.

Orquestan el dominio y hablan con el exterior solo por puertos. No conocen HTTP ni SQL.
"""

from collections.abc import Sequence
from datetime import datetime

from app.domain.deadlines import follow_up_due, valid_until
from app.domain.errors import InvalidLineError, NotFoundError, PermissionDeniedError
from app.domain.events import Event, EventType
from app.domain.parties import ROLES_THAT_SEE_ALL_QUOTES, Actor, Role
from app.domain.pricing_engine import LineInput, LineResult, calculate_line, net_available
from app.domain.quote import Quote, QuoteLine
from app.domain.state_machine import Action, QuoteState, next_state
from app.ports.external import CatalogPort, ClockPort, CustomerPort, EventPort, InventoryPort
from app.ports.repositories import PricingRepository, QuoteRepository


class QuoteService:
    def __init__(
        self,
        quotes: QuoteRepository,
        pricing: PricingRepository,
        catalog: CatalogPort,
        inventory: InventoryPort,
        customers: CustomerPort,
        events: EventPort,
        clock: ClockPort,
    ) -> None:
        self.quotes = quotes
        self.pricing = pricing
        self.catalog = catalog
        self.inventory = inventory
        self.customers = customers
        self.events = events
        self.clock = clock

    # --- Permisos (Tabla 32) -----------------------------------------------------------

    @staticmethod
    def _require_executive(actor: Actor) -> None:
        if actor.rol is not Role.EJECUTIVO:
            raise PermissionDeniedError("Solo un ejecutivo de cuenta puede crear, editar y emitir cotizaciones")

    def _load(self, quote_id: int) -> Quote:
        quote = self.quotes.get(quote_id)
        if quote is None:
            raise NotFoundError(f"La cotización {quote_id} no existe")
        return quote

    def _load_own(self, actor: Actor, quote_id: int) -> Quote:
        self._require_executive(actor)
        quote = self._load(quote_id)
        if quote.ejecutivo_id != actor.id:
            raise PermissionDeniedError("Solo puede modificar sus propias cotizaciones")
        return quote

    def _require_channel(self, canal_id: int) -> None:
        if self.customers.get(canal_id) is None:
            raise NotFoundError(f"El canal {canal_id} no existe")

    # --- Consultas ---------------------------------------------------------------------

    def get(self, actor: Actor, quote_id: int) -> Quote:
        quote = self._load(quote_id)
        if actor.rol is Role.EJECUTIVO and quote.ejecutivo_id == actor.id:
            return quote
        if actor.rol in ROLES_THAT_SEE_ALL_QUOTES:
            return quote
        raise PermissionDeniedError("No tiene permiso para consultar esta cotización")

    def list(self, actor: Actor, estado: QuoteState | None = None) -> Sequence[Quote]:
        if actor.rol is Role.EJECUTIVO:
            return self.quotes.list(ejecutivo_id=actor.id, estado=estado)
        if actor.rol in ROLES_THAT_SEE_ALL_QUOTES:
            return self.quotes.list(estado=estado)
        raise PermissionDeniedError("No tiene permiso para consultar cotizaciones")

    def history(self, actor: Actor, quote_id: int) -> Sequence[Event]:
        self.get(actor, quote_id)
        return self.events.list_for_quote(quote_id)

    # --- Crear y editar ----------------------------------------------------------------

    def create(self, actor: Actor, canal_id: int, recibida_en: datetime, lineas: Sequence[QuoteLine]) -> Quote:
        self._require_executive(actor)
        self._require_channel(canal_id)
        ahora = self.clock.now()
        quote = self.quotes.add(Quote.nueva(canal_id, actor.id, recibida_en, ahora, lineas))
        self.events.record(
            EventType.COTIZACION_CREADA,
            ahora,
            quote.id,
            actor.id,
            {"numero": quote.numero, "canal_id": canal_id, "recibida_en": recibida_en.isoformat(), "lineas": len(quote.lineas)},
        )
        return quote

    def update(
        self, actor: Actor, quote_id: int, canal_id: int, recibida_en: datetime, lineas: Sequence[QuoteLine]
    ) -> Quote:
        quote = self._load_own(actor, quote_id)
        self._require_channel(canal_id)
        ahora = self.clock.now()
        anterior = quote.estado
        quote.editar(canal_id, recibida_en, lineas, ahora)
        self.quotes.save(quote)
        self.events.record(
            EventType.COTIZACION_EDITADA,
            ahora,
            quote.id,
            actor.id,
            {"estado_anterior": anterior, "estado_nuevo": quote.estado, "lineas": len(quote.lineas)},
        )
        return quote

    # --- Calcular (A1 a A4) ------------------------------------------------------------

    def calculate(self, actor: Actor, quote_id: int) -> Quote:
        quote = self._load_own(actor, quote_id)
        if not quote.lineas:
            raise InvalidLineError("Agregue al menos una línea antes de calcular")
        channel = self.customers.get(quote.canal_id)
        if channel is None:
            raise NotFoundError(f"El canal {quote.canal_id} no existe")

        ahora = self.clock.now()
        params = self.pricing.get_params()
        settings = self.pricing.get_settings()
        # RN-04: la fecha de la cotización es el día del cálculo en la zona de la operación.
        fecha = ahora.astimezone(settings.calendar.tz).date()

        resultados: dict[str, LineResult] = {}
        for linea in quote.lineas:
            product = self.catalog.get(linea.referencia)
            if product is None:
                raise InvalidLineError(f"La referencia {linea.referencia} no existe en el catálogo")
            resultados[linea.referencia] = calculate_line(
                LineInput(linea.referencia, linea.cantidad, linea.descuento_adicional),
                product,
                channel.nivel,
                fecha,
                self.pricing.promotions_for(linea.referencia),
                self.inventory.stock(linea.referencia),
                self.quotes.committed_quantity(linea.referencia, ahora),
                params,
            )

        anterior = quote.estado
        quote.calcular(resultados, ahora)
        self.quotes.save(quote)
        self.events.record(
            EventType.COTIZACION_CALCULADA,
            ahora,
            quote.id,
            actor.id,
            {
                "estado_anterior": anterior,
                "estado_nuevo": quote.estado,
                "evaluacion": quote.evaluacion,
                "total": str(quote.total),
                "fecha_cotizacion": fecha.isoformat(),
                "lineas_bajo_pedido": [r.referencia for r in resultados.values() if r.bajo_pedido],
                "lineas_requieren_aprobacion": [r.referencia for r in resultados.values() if r.requiere_aprobacion],
                # RN-04: constancia de las promociones descartadas.
                "promociones_descartadas": [
                    {"referencia": r.referencia, "detalle": regla.descripcion}
                    for r in resultados.values()
                    for regla in r.reglas_aplicadas
                    if regla.regla == "RN-04" and "descartada" in regla.descripcion
                ],
            },
        )
        return quote

    # --- Emitir (A6) -------------------------------------------------------------------

    def issue(self, actor: Actor, quote_id: int) -> Quote:
        quote = self._load_own(actor, quote_id)
        # Se valida la transición antes de consultar el ERP: falla rápido y con el motivo exacto.
        next_state(quote.estado, Action.EMITIR, quote.contexto)
        ahora = self.clock.now()
        settings = self.pricing.get_settings()

        fines_promocion = [
            linea.resultado.promocion_fin
            for linea in quote.lineas
            if linea.resultado is not None and linea.resultado.promocion_fin is not None
        ]
        vigente_hasta = valid_until(ahora, settings.vigencia_minutos, fines_promocion, settings.calendar.tz)
        seguimiento_en = follow_up_due(ahora, settings.seguimiento_minutos)
        disponibles = {
            linea.referencia: net_available(
                self.inventory.stock(linea.referencia), self.quotes.committed_quantity(linea.referencia, ahora)
            )
            for linea in quote.lineas
        }

        anterior = quote.estado
        quote.emitir(ahora, vigente_hasta, seguimiento_en, disponibles)
        self.quotes.save(quote)
        self.events.record(
            EventType.COTIZACION_EMITIDA,
            ahora,
            quote.id,
            actor.id,
            {
                "estado_anterior": anterior,
                "estado_nuevo": quote.estado,
                "total": str(quote.total),
                "recibida_en": quote.recibida_en.isoformat(),
                "vigente_hasta": vigente_hasta.isoformat(),
                "inventario_comprometido": {l.referencia: l.cantidad_comprometida for l in quote.lineas},
            },
        )
        self.events.record(
            EventType.SEGUIMIENTO_PROGRAMADO, ahora, quote.id, None, {"programado_para": seguimiento_en.isoformat()}
        )
        return quote
