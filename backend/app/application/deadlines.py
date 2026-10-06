"""Procesamiento periódico de plazos vencidos. Es lo que ejecuta el planificador en cada ciclo."""

from dataclasses import dataclass

from app.application.approvals import ApprovalService
from app.application.followup import FollowUpService
from app.ports.external import ClockPort


@dataclass(frozen=True)
class DeadlineReport:
    vencidas: int
    seguimientos: int
    escaladas: int

    @property
    def total(self) -> int:
        return self.vencidas + self.seguimientos + self.escaladas


class DeadlineService:
    def __init__(self, approvals: ApprovalService, followup: FollowUpService, clock: ClockPort) -> None:
        self.approvals = approvals
        self.followup = followup
        self.clock = clock

    def process(self) -> DeadlineReport:
        """Revisa en la base de datos qué plazos se cumplieron. Es idempotente: repetirlo no
        duplica nada, y si la aplicación estuvo caída, al volver se pone al día."""
        ahora = self.clock.now()
        # Primero la vigencia: una cotización vencida ya no necesita seguimiento.
        vencidas = self.followup.expire_due(ahora)
        seguimientos = self.followup.start_due_follow_ups(ahora)
        escaladas = self.approvals.escalate_overdue(ahora)
        return DeadlineReport(vencidas, seguimientos, escaladas)
