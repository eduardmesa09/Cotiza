import { AlertTriangle, Ban, ChevronDown, ChevronRight, PackageX, Trash2 } from "lucide-react";
import { Fragment, useState } from "react";
import { formatDate, formatMoney, formatPercent } from "../lib/format";
import type { QuoteLine } from "../lib/types";
import { Badge, Table, TD, TH } from "./ui";

/** Una línea en pantalla: lo que el ejecutivo escribe más, si existe, el último cálculo. */
export interface ViewLine {
  referencia: string;
  descripcion: string;
  cantidad: string;
  /** Descuento adicional como porcentaje escrito por el usuario ("9" = 9 %). */
  adicional: string;
  result?: QuoteLine;
}

interface Props {
  lines: ViewLine[];
  editable?: boolean;
  /** El cálculo mostrado ya no corresponde a lo escrito: se atenúa hasta recalcular. */
  stale?: boolean;
  onChange?: (index: number, patch: Partial<Pick<ViewLine, "cantidad" | "adicional">>) => void;
  onRemove?: (index: number) => void;
}

/** Alertas de una línea calculada, en el orden en que bloquean. */
export function lineAlerts(line: QuoteLine): { key: string; label: string; tone: "bad" | "warn" }[] {
  const alerts: { key: string; label: string; tone: "bad" | "warn" }[] = [];
  if (line.estado === "NO_COTIZABLE") alerts.push({ key: "no-cotizable", label: "No cotizable", tone: "bad" });
  if (line.estado === "BAJO_COSTO") alerts.push({ key: "bajo-costo", label: "Bajo costo", tone: "bad" });
  if (line.requiere_aprobacion && line.estado !== "BAJO_COSTO") {
    alerts.push({ key: "aprobacion", label: "Requiere aprobación", tone: "warn" });
  }
  if (line.bajo_pedido) alerts.push({ key: "bajo-pedido", label: "Bajo pedido", tone: "warn" });
  return alerts;
}

const ALERT_ICON = {
  "no-cotizable": <Ban className="size-3" aria-hidden />,
  "bajo-costo": <Ban className="size-3" aria-hidden />,
  aprobacion: <AlertTriangle className="size-3" aria-hidden />,
  "bajo-pedido": <PackageX className="size-3" aria-hidden />,
} as const;

const NUMBER_INPUT =
  "nums w-20 rounded-lg border border-line bg-surface px-2 py-1.5 text-right text-sm focus:border-brand focus:outline-2 focus:outline-brand/25";

export function LinesTable({ lines, editable = false, stale = false, onChange, onRemove }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const dim = stale ? "opacity-40" : "";

  return (
    <Table
      head={
        <tr>
          <th className={TH}>Referencia</th>
          <th className={`${TH} text-right`}>Cantidad</th>
          <th className={`${TH} text-right`}>Desc. adicional</th>
          <th className={`${TH} text-right`}>Precio de lista</th>
          <th className={`${TH} text-right`}>Precio unitario</th>
          <th className={`${TH} text-right`}>Margen</th>
          <th className={`${TH} text-right`}>Total</th>
          <th className={TH}>Disponibilidad</th>
          {editable && <th className={TH} />}
        </tr>
      }
    >
      {lines.map((line, index) => {
        const r = line.result;
        const alerts = r ? lineAlerts(r) : [];
        const open = expanded === line.referencia && r !== undefined;
        const belowMin = r?.margen != null && r.margen_minimo != null && Number(r.margen) < Number(r.margen_minimo);
        return (
          <Fragment key={line.referencia}>
            <tr>
              <td className={TD}>
                <div className="flex items-start gap-1.5">
                  {r && r.reglas_aplicadas.length > 0 ? (
                    <button
                      type="button"
                      onClick={() => setExpanded(open ? null : line.referencia)}
                      aria-expanded={open}
                      aria-label={`${open ? "Ocultar" : "Ver"} reglas aplicadas a ${line.referencia}`}
                      className="mt-0.5 rounded p-0.5 text-muted hover:bg-canvas hover:text-ink"
                    >
                      {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    </button>
                  ) : (
                    <span className="w-5" />
                  )}
                  <div className="min-w-0">
                    <p className="font-semibold text-ink">{line.referencia}</p>
                    <p className="max-w-xs text-xs text-muted">{line.descripcion}</p>
                    {alerts.length > 0 && (
                      <div className={`mt-1.5 flex flex-wrap gap-1 ${dim}`}>
                        {alerts.map((a) => (
                          <Badge key={a.key} tone={a.tone} icon={ALERT_ICON[a.key as keyof typeof ALERT_ICON]}>
                            {a.label}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </td>
              <td className={`${TD} text-right`}>
                {editable ? (
                  <input
                    type="number"
                    min={1}
                    step={1}
                    aria-label={`Cantidad de ${line.referencia}`}
                    value={line.cantidad}
                    onChange={(e) => onChange?.(index, { cantidad: e.target.value })}
                    className={NUMBER_INPUT}
                  />
                ) : (
                  <span className="nums">{line.cantidad}</span>
                )}
              </td>
              <td className={`${TD} text-right`}>
                {editable ? (
                  <span className="inline-flex items-center gap-1">
                    <input
                      type="number"
                      min={0}
                      max={99.99}
                      step={0.5}
                      aria-label={`Descuento adicional de ${line.referencia} en porcentaje`}
                      value={line.adicional}
                      onChange={(e) => onChange?.(index, { adicional: e.target.value })}
                      className={NUMBER_INPUT}
                    />
                    <span className="text-muted">%</span>
                  </span>
                ) : (
                  <span className="nums">{Number(line.adicional) > 0 ? `${line.adicional.replace(".", ",")} %` : "—"}</span>
                )}
              </td>
              <td className={`${TD} nums text-right ${dim}`}>{formatMoney(r?.precio_lista, false)}</td>
              <td className={`${TD} nums text-right font-semibold ${dim}`}>{formatMoney(r?.precio_unitario, false)}</td>
              <td className={`${TD} text-right ${dim}`}>
                <span className={`nums font-medium ${belowMin ? "text-bad" : "text-ink"}`}>{formatPercent(r?.margen)}</span>
                {r?.margen_minimo != null && <span className="block text-xs text-muted">mín. {formatPercent(r.margen_minimo)}</span>}
              </td>
              <td className={`${TD} nums text-right font-semibold ${dim}`}>{formatMoney(r?.total, false)}</td>
              <td className={`${TD} ${dim}`}>
                {r?.disponible == null ? (
                  <span className="text-muted">—</span>
                ) : (
                  <span className="nums text-sm">
                    {r.disponible} u<span className="block text-xs text-muted">disponibles</span>
                  </span>
                )}
              </td>
              {editable && (
                <td className={`${TD} text-right`}>
                  <button
                    type="button"
                    onClick={() => onRemove?.(index)}
                    aria-label={`Quitar ${line.referencia}`}
                    className="rounded-full p-1.5 text-muted hover:bg-red-50 hover:text-bad"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </td>
              )}
            </tr>
            {open && r && (
              <tr className="bg-canvas/60">
                <td colSpan={editable ? 9 : 8} className="px-10 py-3">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Reglas aplicadas</p>
                  <ol className="space-y-1.5 text-sm">
                    {r.reglas_aplicadas.map((rule, i) => (
                      <li key={i} className="flex items-baseline justify-between gap-4">
                        <span>
                          <span className="mr-2 rounded bg-surface px-1.5 py-0.5 text-xs font-semibold text-brand-dark ring-1 ring-line">{rule.regla}</span>
                          {rule.descripcion}
                        </span>
                        {rule.precio_resultante && <span className="nums shrink-0 text-muted">→ {formatMoney(rule.precio_resultante, false)}</span>}
                      </li>
                    ))}
                  </ol>
                  {r.promocion_fin && <p className="mt-2 text-xs text-muted">La promoción aplicada termina el {formatDate(r.promocion_fin)} y acota la vigencia.</p>}
                </td>
              </tr>
            )}
          </Fragment>
        );
      })}
    </Table>
  );
}
