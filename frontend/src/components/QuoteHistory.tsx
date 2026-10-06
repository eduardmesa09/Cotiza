import { formatDateTime, formatDuration, formatMoney } from "../lib/format";
import type { QuoteEvent } from "../lib/types";
import { useApi } from "../lib/useApi";
import { Loading } from "./ui";

const LABEL: Record<string, string> = {
  COTIZACION_CREADA: "Cotización creada",
  COTIZACION_EDITADA: "Líneas editadas",
  COTIZACION_CALCULADA: "Precio calculado",
  APROBACION_SOLICITADA: "Aprobación solicitada",
  APROBACION_APROBADA: "Descuento aprobado",
  APROBACION_RECHAZADA: "Descuento rechazado",
  APROBACION_ESCALADA: "Escalada a gerencia por SLA vencido",
  COTIZACION_EMITIDA: "Cotización emitida",
  SEGUIMIENTO_PROGRAMADO: "Seguimiento programado",
  SEGUIMIENTO_INICIADO: "Tarea de seguimiento creada",
  SEGUIMIENTO_MANTENIDO: "Se mantiene en seguimiento",
  COTIZACION_GANADA: "Ganada",
  COTIZACION_PERDIDA: "Perdida",
  COTIZACION_VENCIDA: "Vencida: inventario liberado",
  COTIZACION_REEMPLAZADA: "Reemplazada por una nueva versión",
  NUEVA_VERSION_CREADA: "Nueva versión creada",
};

const EVALUATION: Record<string, string> = {
  LISTA_PARA_EMITIR: "lista para emitir",
  REQUIERE_APROBACION: "requiere aprobación",
  NO_EMITIBLE: "no emitible",
};

/** Dato más útil de cada evento, en una frase. */
function detail(event: QuoteEvent): string | null {
  const p = event.payload as Record<string, any>;
  switch (event.tipo) {
    case "COTIZACION_CALCULADA": {
      const parts = [`Total ${formatMoney(p.total)}`, EVALUATION[p.evaluacion] ?? ""];
      const discarded = (p.promociones_descartadas as unknown[] | undefined)?.length ?? 0;
      if (discarded) parts.push(`${discarded} promoción${discarded > 1 ? "es" : ""} descartada${discarded > 1 ? "s" : ""}`);
      return parts.filter(Boolean).join(" · ");
    }
    case "APROBACION_SOLICITADA":
      return `Vence ${formatDateTime(p.vence_en)}`;
    case "APROBACION_APROBADA":
    case "APROBACION_RECHAZADA":
      return `«${p.comentario}» · espera de ${formatDuration(p.espera_segundos)}${p.dentro_del_sla ? "" : " (fuera del SLA)"}`;
    case "COTIZACION_EMITIDA":
      return `Total ${formatMoney(p.total)} · vigente hasta ${formatDateTime(p.vigente_hasta)}`;
    case "SEGUIMIENTO_PROGRAMADO":
    case "SEGUIMIENTO_MANTENIDO":
      return `Próximo recordatorio: ${formatDateTime(p.programado_para)}${p.nota ? ` · «${p.nota}»` : ""}`;
    case "COTIZACION_GANADA":
    case "COTIZACION_PERDIDA":
      return p.nota ? `«${p.nota}»` : null;
    case "NUEVA_VERSION_CREADA":
      return `Versión ${p.version}`;
    default:
      return null;
  }
}

/** Historial de eventos de la cotización: la pista de auditoría que registra el sistema. */
export function QuoteHistory({ quoteId, refreshKey }: { quoteId: number; refreshKey: unknown }) {
  // refreshKey cambia tras cada acción; al ir en la ruta fuerza una nueva carga.
  const { data, loading, error } = useApi<QuoteEvent[]>(`/cotizaciones/${quoteId}/eventos?_=${String(refreshKey)}`);
  if (loading && !data) return <Loading label="Cargando historial…" />;
  if (error) return <p className="text-sm text-bad">{error}</p>;
  return (
    <ol className="relative space-y-4 border-l border-line pl-5">
      {data?.map((event) => {
        const extra = detail(event);
        return (
          <li key={event.id} className="relative">
            <span className="absolute -left-[25px] top-1.5 size-2.5 rounded-full bg-brand ring-4 ring-surface" aria-hidden />
            <p className="text-sm font-medium text-ink">{LABEL[event.tipo] ?? event.tipo}</p>
            {extra && <p className="text-sm text-muted">{extra}</p>}
            <p className="mt-0.5 text-xs text-muted">
              {formatDateTime(event.ocurrido_en)} · {event.usuario ?? "Sistema"}
            </p>
          </li>
        );
      })}
    </ol>
  );
}
