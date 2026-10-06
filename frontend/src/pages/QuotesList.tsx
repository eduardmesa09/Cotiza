import { FileText, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useUser } from "../auth/AuthContext";
import { Card, EmptyState, ErrorNotice, Loading, PageHeader, STATE_LABEL, StateBadge, Table, TD, TH } from "../components/ui";
import { formatDateTime, formatMoney } from "../lib/format";
import type { QuoteState, QuoteSummary } from "../lib/types";
import { useApi } from "../lib/useApi";

const STATES = Object.keys(STATE_LABEL) as QuoteState[];

export function QuotesList() {
  const user = useUser();
  const navigate = useNavigate();
  const [state, setState] = useState<QuoteState | "">("");
  const { data, loading, error } = useApi<QuoteSummary[]>(`/cotizaciones${state ? `?estado=${state}` : ""}`, 30_000);
  const own = user.rol === "ejecutivo";

  return (
    <>
      <PageHeader
        title={own ? "Mis cotizaciones" : "Cotizaciones"}
        subtitle={own ? "Todo lo que ha cotizado, con su estado actual." : "Repositorio central de cotizaciones."}
        actions={
          own && (
            <Link to="/cotizaciones/nueva" className="inline-flex items-center gap-2 rounded-full bg-brand px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-brand-mid">
              <Plus className="size-4" aria-hidden />
              Nueva cotización
            </Link>
          )
        }
      />

      <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label="Filtrar por estado">
        {(["", ...STATES] as const).map((value) => (
          <button
            key={value || "todas"}
            type="button"
            aria-pressed={state === value}
            onClick={() => setState(value)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
              state === value ? "bg-brand-dark text-white" : "bg-surface text-muted shadow-card hover:text-ink"
            }`}
          >
            {value ? STATE_LABEL[value] : "Todas"}
          </button>
        ))}
      </div>

      <Card className="p-0">
        <ErrorNotice message={error} />
        {loading && !data ? (
          <Loading />
        ) : !data?.length ? (
          <EmptyState icon={<FileText className="size-6" />} title="No hay cotizaciones">
            {state ? "Ninguna cotización está en ese estado." : own ? "Cree la primera con «Nueva cotización»." : "Todavía no se ha registrado ninguna."}
          </EmptyState>
        ) : (
          <Table
            head={
              <tr>
                <th className={`${TH} pl-5`}>Número</th>
                <th className={TH}>Canal</th>
                {!own && <th className={TH}>Ejecutivo</th>}
                <th className={TH}>Estado</th>
                <th className={`${TH} text-right`}>Líneas</th>
                <th className={`${TH} text-right`}>Total</th>
                <th className={TH}>Creada</th>
                <th className={`${TH} pr-5`}>Vigente hasta</th>
              </tr>
            }
          >
            {data.map((q) => (
              <tr key={q.id} onClick={() => navigate(`/cotizaciones/${q.id}`)} className="cursor-pointer hover:bg-canvas/70">
                <td className={`${TD} pl-5`}>
                  <Link to={`/cotizaciones/${q.id}`} onClick={(e) => e.stopPropagation()} className="font-semibold text-brand hover:underline">
                    {q.numero}
                  </Link>
                  {q.version > 1 && <span className="ml-1.5 text-xs text-muted">v{q.version}</span>}
                </td>
                <td className={TD}>
                  {q.canal.nombre}
                  <span className="block text-xs text-muted">Nivel {q.canal.nivel}</span>
                </td>
                {!own && <td className={TD}>{q.ejecutivo.nombre}</td>}
                <td className={TD}>
                  <StateBadge state={q.estado} replaced={q.reemplazada} />
                </td>
                <td className={`${TD} nums text-right`}>{q.lineas_count}</td>
                <td className={`${TD} nums text-right font-medium`}>{formatMoney(q.total)}</td>
                <td className={`${TD} text-muted`}>{formatDateTime(q.creada_en)}</td>
                <td className={`${TD} pr-5 text-muted`}>{formatDateTime(q.vigente_hasta)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}
