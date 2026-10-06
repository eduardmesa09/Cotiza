import { ArrowDownRight, ArrowUpRight, CheckCircle2, CircleDashed, Timer } from "lucide-react";
import { Card, ErrorNotice, Loading, PageHeader, Table, TD, TH } from "../components/ui";
import { formatDateTime, formatKpi } from "../lib/format";
import type { Dashboard as DashboardData, Kpi } from "../lib/types";
import { useApi } from "../lib/useApi";

/** Cuánto mejoró un indicador frente a la línea base AS-IS, y si ya cumple la meta. */
export function assess(kpi: Kpi): { changePct: number | null; improved: boolean | null; meetsTarget: boolean | null } {
  if (kpi.valor === null) return { changePct: null, improved: null, meetsTarget: null };
  const lowerIsBetter = kpi.sentido === "menor";
  const meetsTarget = kpi.meta === null ? null : lowerIsBetter ? kpi.valor <= kpi.meta : kpi.valor >= kpi.meta;
  if (kpi.linea_base === null || kpi.linea_base === 0) return { changePct: null, improved: null, meetsTarget };
  const changePct = ((kpi.valor - kpi.linea_base) / kpi.linea_base) * 100;
  // Sin meta definida el indicador es solo de contexto: se muestra la variación, sin calificarla.
  const improved = kpi.meta === null || changePct === 0 ? null : lowerIsBetter ? changePct < 0 : changePct > 0;
  return { changePct, improved, meetsTarget };
}

function signed(pct: number): string {
  const rounded = Math.round(pct);
  return `${rounded > 0 ? "+" : rounded < 0 ? "−" : ""}${Math.abs(rounded)} %`;
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-4 rounded-sm bg-chart-base" aria-hidden /> Línea base (proceso manual)
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-4 rounded-sm bg-brand" aria-hidden /> COTIZA+ (medido)
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3.5 w-0.5 bg-ink" aria-hidden /> Meta
      </span>
    </div>
  );
}

/** Dos barras en la misma escala (línea base y valor medido) y una marca para la meta. */
function ComparisonBars({ kpi }: { kpi: Kpi }) {
  const max = Math.max(kpi.linea_base ?? 0, kpi.valor ?? 0, kpi.meta ?? 0) || 1;
  const width = (value: number | null) => `${Math.max(((value ?? 0) / max) * 100, value ? 1.5 : 0)}%`;
  const rows = [
    { label: "Línea base", value: kpi.linea_base, color: "bg-chart-base" },
    { label: "COTIZA+", value: kpi.valor, color: "bg-brand" },
  ];
  return (
    <div className="relative mt-4 space-y-0.5">
      {rows.map((row) => (
        <div key={row.label} className="flex items-center gap-2" title={`${row.label}: ${formatKpi(row.value, kpi.unidad)}`}>
          <div className="h-3 flex-1 rounded-r bg-canvas">
            {row.value !== null && <div className={`h-3 rounded-r ${row.color}`} style={{ width: width(row.value) }} />}
          </div>
          <span className="nums w-20 shrink-0 text-right text-xs text-muted">{formatKpi(row.value, kpi.unidad)}</span>
        </div>
      ))}
      {kpi.meta !== null && (
        // La marca vive sobre el área de las barras, que ocupa todo menos la columna de valores (5rem + separación).
        <div className="pointer-events-none absolute inset-y-0 left-0 right-[5.5rem]" aria-hidden>
          <div className="absolute -inset-y-1 w-0.5 bg-ink" style={{ left: `${(kpi.meta / max) * 100}%` }} />
        </div>
      )}
    </div>
  );
}

export function KpiCard({ kpi }: { kpi: Kpi }) {
  const { changePct, improved, meetsTarget } = assess(kpi);
  const Arrow = changePct !== null && changePct < 0 ? ArrowDownRight : ArrowUpRight;
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-medium text-muted">{kpi.nombre}</h3>
        <span className="rounded-full bg-canvas px-2 py-0.5 text-[11px] font-semibold text-muted">{kpi.codigo}</span>
      </div>
      <p className="nums mt-2 text-4xl font-semibold tracking-tight text-ink">
        {kpi.valor === null ? <span className="text-2xl font-medium text-muted">Sin datos todavía</span> : formatKpi(kpi.valor, kpi.unidad)}
      </p>
      <div className="mt-1.5 flex min-h-5 flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {changePct !== null && (
          <span className={`inline-flex items-center gap-0.5 font-semibold ${improved === null ? "text-muted" : improved ? "text-ok" : "text-bad"}`}>
            <Arrow className="size-3.5" aria-hidden />
            {signed(changePct)}{" "}
            <span className="font-normal text-muted">
              frente a la línea base{improved !== null && ` · ${improved ? "mejora" : "empeora"}`}
            </span>
          </span>
        )}
        {meetsTarget !== null && (
          <span className="inline-flex items-center gap-1 text-muted">
            {meetsTarget ? <CheckCircle2 className="size-3.5 text-ok" aria-hidden /> : <CircleDashed className="size-3.5" aria-hidden />}
            {meetsTarget ? "Cumple la meta" : "Aún no cumple la meta"} ({formatKpi(kpi.meta, kpi.unidad)})
          </span>
        )}
      </div>
      {kpi.linea_base !== null && <ComparisonBars kpi={kpi} />}
      <p className="mt-3 text-xs text-muted" title={kpi.formula}>
        {kpi.muestra === 0 ? "Sin casos aún" : `${kpi.muestra} ${kpi.muestra === 1 ? "caso" : "casos"}`} · {kpi.formula}
      </p>
    </Card>
  );
}

const TOTALS: [string, string][] = [
  ["creadas", "Creadas"],
  ["emitidas", "Emitidas"],
  ["ganadas", "Ganadas"],
  ["perdidas", "Perdidas"],
  ["vencidas", "Vencidas"],
  ["reemplazadas", "Con nueva versión"],
];

export function Dashboard() {
  // Se recalcula desde los eventos en cada consulta; se refresca cada 30 s.
  const { data, loading, error } = useApi<DashboardData>("/kpis", 30_000);
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorNotice message={error} />;

  const hero = data.indicadores.find((k) => k.codigo === "K2");
  const heroAssessment = hero ? assess(hero) : null;
  const rest = data.indicadores.filter((k) => k.codigo !== "K2");

  return (
    <>
      <PageHeader
        title="Indicadores"
        subtitle={`${data.alcance === "propios" ? "Sus cotizaciones" : "Todas las cotizaciones"} · calculado desde el registro de eventos · ${formatDateTime(data.generado_en)}`}
        actions={<Legend />}
      />

      <div className="grid gap-5 lg:grid-cols-3">
        {hero && (
          <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand via-brand-mid to-brand-dark p-6 text-white shadow-card lg:col-span-2">
            <div className="absolute -right-10 -top-16 size-64 rounded-full bg-white/10" aria-hidden />
            <div className="absolute -bottom-24 right-24 size-56 rounded-full bg-white/5" aria-hidden />
            <p className="text-xs font-semibold uppercase tracking-widest text-white/70">Tiempo de elaboración por cotización</p>
            <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-2">
              <div className="flex items-center gap-3">
                <span className="flex size-12 items-center justify-center rounded-full bg-white/15">
                  <Timer className="size-6" aria-hidden />
                </span>
                <span className="nums text-6xl font-semibold tracking-tight">{hero.valor === null ? "—" : formatKpi(hero.valor, "")}</span>
                <span className="pb-2 text-lg text-white/80">min</span>
              </div>
              <p className="pb-2 text-white/80">
                frente a <span className="nums font-semibold text-white">{formatKpi(hero.linea_base, "min")}</span> del proceso manual
              </p>
            </div>
            <p className="mt-4 max-w-xl text-lg leading-snug">
              {hero.valor === null
                ? "Emita la primera cotización para medir el tiempo de elaboración."
                : heroAssessment?.improved
                  ? `Una reducción del ${Math.abs(Math.round(heroAssessment.changePct ?? 0))} % en el esfuerzo de cotizar.`
                  : "El tiempo medido todavía no mejora la línea base."}
            </p>
            <p className="mt-4 text-sm text-white/70">
              Meta: {formatKpi(hero.meta, "min")} · {hero.muestra} {hero.muestra === 1 ? "cotización emitida" : "cotizaciones emitidas"} · {hero.formula}
            </p>
          </section>
        )}

        <Card>
          <h2 className="text-sm font-medium text-muted">Cotizaciones</h2>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-4">
            {TOTALS.map(([key, label]) => (
              <div key={key}>
                <dd className="nums text-3xl font-semibold tracking-tight">{data.totales[key] ?? 0}</dd>
                <dt className="text-xs text-muted">{label}</dt>
              </div>
            ))}
          </dl>
        </Card>
      </div>

      <div className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {rest.map((kpi) => (
          <KpiCard key={kpi.codigo} kpi={kpi} />
        ))}
      </div>

      <details className="mt-5 rounded-2xl bg-surface p-5 shadow-card">
        <summary className="cursor-pointer text-sm font-medium text-ink">Ver los indicadores como tabla</summary>
        <div className="mt-3">
          <Table
            head={
              <tr>
                <th className={TH}>Indicador</th>
                <th className={`${TH} text-right`}>Línea base</th>
                <th className={`${TH} text-right`}>COTIZA+</th>
                <th className={`${TH} text-right`}>Meta</th>
                <th className={`${TH} text-right`}>Casos</th>
                <th className={TH}>Fórmula</th>
              </tr>
            }
          >
            {data.indicadores.map((k) => (
              <tr key={k.codigo}>
                <td className={TD}>
                  <span className="font-medium">{k.nombre}</span> <span className="text-xs text-muted">{k.codigo}</span>
                </td>
                <td className={`${TD} nums text-right`}>{formatKpi(k.linea_base, k.unidad)}</td>
                <td className={`${TD} nums text-right font-semibold`}>{formatKpi(k.valor, k.unidad)}</td>
                <td className={`${TD} nums text-right`}>{formatKpi(k.meta, k.unidad)}</td>
                <td className={`${TD} nums text-right`}>{k.muestra}</td>
                <td className={`${TD} text-muted`}>{k.formula}</td>
              </tr>
            ))}
          </Table>
        </div>
      </details>
    </>
  );
}
