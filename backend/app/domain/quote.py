"""La cotización y sus líneas. Toda modificación de estado pasa por la máquina de estados."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.domain.errors import InvalidLineError
from app.domain.pricing_engine import (
    ONE,
    ZERO,
    Evaluation,
    LineResult,
    evaluate_quote,
    quote_total,
)
from app.domain.state_machine import (
    Action,
    QuoteState,
    TransitionContext,
    allowed_actions,
    next_state,
)


@dataclass
class QuoteLine:
    referencia: str
    cantidad: int
    descuento_adicional: Decimal = ZERO
    # Foto del último cálculo; None mientras la línea no se haya calculado.
    resultado: LineResult | None = None
    # Unidades comprometidas del inventario desde la emisión (RN-10).
    cantidad_comprometida: int = 0
    # Disponibilidad vista al emitir; puede diferir de la del cálculo.
    disponible: int | None = None
    bajo_pedido: bool = False


def validate_lines(lineas: Sequence[QuoteLine]) -> None:
    referencias = set()
    for linea in lineas:
        if not linea.referencia:
            raise InvalidLineError("Cada línea debe indicar una referencia")
        if linea.referencia in referencias:
            raise InvalidLineError(f"La referencia {linea.referencia} está repetida: use una sola línea")
        referencias.add(linea.referencia)
        if linea.cantidad <= 0:
            raise InvalidLineError(f"La cantidad de {linea.referencia} debe ser mayor que cero")
        if not ZERO <= linea.descuento_adicional < ONE:
            raise InvalidLineError(
                f"El descuento adicional de {linea.referencia} debe estar entre 0 % y menos de 100 %"
            )


def _validate_reception(recibida_en: datetime, ahora: datetime) -> None:
    if recibida_en > ahora:
        raise InvalidLineError("La hora de recepción de la solicitud no puede estar en el futuro")


@dataclass
class Quote:
    canal_id: int
    ejecutivo_id: int
    recibida_en: datetime
    creada_en: datetime
    lineas: list[QuoteLine] = field(default_factory=list)
    estado: QuoteState = QuoteState.BORRADOR
    evaluacion: Evaluation | None = None
    total: Decimal | None = None
    id: int | None = None
    numero: str = ""
    version: int = 1
    version_anterior_id: int | None = None
    reemplazada: bool = False
    calculada_en: datetime | None = None
    emitida_en: datetime | None = None
    vigente_hasta: datetime | None = None
    proximo_seguimiento_en: datetime | None = None
    cerrada_en: datetime | None = None
    pdf_ruta: str | None = None
    # La solicitud de aprobación vigente fue aprobada (falta que el ejecutivo confirme).
    aprobada: bool = False

    @classmethod
    def nueva(
        cls,
        canal_id: int,
        ejecutivo_id: int,
        recibida_en: datetime,
        ahora: datetime,
        lineas: Sequence[QuoteLine] = (),
    ) -> "Quote":
        _validate_reception(recibida_en, ahora)
        validate_lines(lineas)
        return cls(canal_id=canal_id, ejecutivo_id=ejecutivo_id, recibida_en=recibida_en, creada_en=ahora, lineas=list(lineas))

    @property
    def contexto(self) -> TransitionContext:
        return TransitionContext(evaluacion=self.evaluacion, aprobada=self.aprobada)

    @property
    def acciones_permitidas(self) -> frozenset[Action]:
        return allowed_actions(self.estado, self.contexto)

    def _transition(self, accion: Action) -> None:
        self.estado = next_state(self.estado, accion, self.contexto)

    def editar(self, canal_id: int, recibida_en: datetime, lineas: Sequence[QuoteLine], ahora: datetime) -> None:
        """Cambia canal, recepción o líneas. Invalida el cálculo anterior: vuelve a BORRADOR."""
        _validate_reception(recibida_en, ahora)
        validate_lines(lineas)
        self._transition(Action.EDITAR)
        self.canal_id = canal_id
        self.recibida_en = recibida_en
        self.lineas = list(lineas)
        self.evaluacion = None
        self.total = None
        self.calculada_en = None

    def calcular(self, resultados: Mapping[str, LineResult], ahora: datetime) -> None:
        """Registra el resultado del motor de reglas para cada línea (por referencia)."""
        self._transition(Action.CALCULAR)
        for linea in self.lineas:
            linea.resultado = resultados[linea.referencia]
            linea.disponible = linea.resultado.disponible
            linea.bajo_pedido = linea.resultado.bajo_pedido
        calculadas = [linea.resultado for linea in self.lineas]
        self.evaluacion = evaluate_quote(calculadas)
        self.total = quote_total(calculadas)
        self.calculada_en = ahora

    def emitir(
        self,
        ahora: datetime,
        vigente_hasta: datetime,
        proximo_seguimiento_en: datetime,
        disponibles: Mapping[str, int],
    ) -> None:
        """Emite: congela precios (RN-13) y compromete inventario de lo disponible (RN-10).

        `disponibles` es la disponibilidad neta de cada referencia en este momento. Los
        precios no se tocan: quedan los del último cálculo.
        """
        self._transition(Action.EMITIR)
        for linea in self.lineas:
            disponible = disponibles[linea.referencia]
            linea.disponible = disponible
            linea.bajo_pedido = linea.cantidad > disponible
            linea.cantidad_comprometida = min(linea.cantidad, disponible)
        self.emitida_en = ahora
        self.vigente_hasta = vigente_hasta
        self.proximo_seguimiento_en = proximo_seguimiento_en
