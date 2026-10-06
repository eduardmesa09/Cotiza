"""Armado de los casos de uso con los adaptadores del MVP.

Es el único lugar donde se decide qué adaptador implementa cada puerto. Lo usan la API (una
sesión por petición) y el planificador (una sesión por ciclo).
"""

from sqlalchemy.orm import Session

from app.adapters.sql_misc import SqlCustomerAdapter, SqlEventAdapter, SqlNotificationAdapter, SqlUserDirectory
from app.adapters.sql_repositories import (
    SqlApprovalRepository,
    SqlFollowUpRepository,
    SqlPricingRepository,
    SqlQuoteRepository,
)
from app.application.approvals import ApprovalService
from app.application.deadlines import DeadlineService
from app.application.followup import FollowUpService
from app.application.quotes import QuoteService
from app.ports.external import CatalogPort, ClockPort, InventoryPort


def build_quote_service(session: Session, catalog: CatalogPort, inventory: InventoryPort, clock: ClockPort) -> QuoteService:
    return QuoteService(
        quotes=SqlQuoteRepository(session),
        pricing=SqlPricingRepository(session),
        catalog=catalog,
        inventory=inventory,
        customers=SqlCustomerAdapter(session),
        events=SqlEventAdapter(session),
        clock=clock,
    )


def build_approval_service(session: Session, clock: ClockPort) -> ApprovalService:
    return ApprovalService(
        quotes=SqlQuoteRepository(session),
        approvals=SqlApprovalRepository(session),
        pricing=SqlPricingRepository(session),
        events=SqlEventAdapter(session),
        notifications=SqlNotificationAdapter(session),
        users=SqlUserDirectory(session),
        clock=clock,
    )


def build_followup_service(session: Session, clock: ClockPort) -> FollowUpService:
    return FollowUpService(
        quotes=SqlQuoteRepository(session),
        tasks=SqlFollowUpRepository(session),
        pricing=SqlPricingRepository(session),
        events=SqlEventAdapter(session),
        notifications=SqlNotificationAdapter(session),
        clock=clock,
    )


def build_deadline_service(session: Session, clock: ClockPort) -> DeadlineService:
    return DeadlineService(build_approval_service(session, clock), build_followup_service(session, clock), clock)
