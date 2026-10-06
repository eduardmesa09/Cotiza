from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_current_user, get_kpi_service
from app.api.schemas import DashboardOut
from app.application.kpis import KpiService

router = APIRouter(prefix="/api/kpis", tags=["Indicadores"])


@router.get("", response_model=DashboardOut)
def dashboard(
    user: CurrentUser = Depends(get_current_user), service: KpiService = Depends(get_kpi_service)
) -> DashboardOut:
    """Indicadores calculados desde el registro de eventos, frente a la línea base AS-IS y la meta.
    El ejecutivo ve los de sus cotizaciones; aprobador, gerente y pricing, los de todas."""
    result = service.dashboard(user.actor)
    return DashboardOut(
        alcance=result.alcance,
        generado_en=result.generado_en,
        totales=result.reporte.totales,
        indicadores=result.reporte.indicadores,
    )
