import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorNotice, Field, Input, Loading, Modal, PageHeader, Table, TD, TH } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, formatPercent, fractionToPercentInput, percentInputToFraction } from "../lib/format";
import type { Level, Margin, Parameter, Promotion, VolumeTier } from "../lib/types";
import { useApi } from "../lib/useApi";

// --- Edición de un porcentaje en línea ------------------------------------------------

function PercentEditor({ fraction, label, onSave }: { fraction: string; label: string; onSave: (fraction: string) => Promise<void> }) {
  const [value, setValue] = useState(fractionToPercentInput(fraction));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const changed = percentInputToFraction(value) !== Number(fraction).toFixed(4);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await onSave(percentInputToFraction(value));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-end gap-2">
        <input
          type="number"
          min={0}
          max={99.99}
          step={0.5}
          aria-label={label}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="nums w-24 rounded-lg border border-line px-2 py-1.5 text-right text-sm focus:border-brand focus:outline-2 focus:outline-brand/25"
        />
        <span className="text-muted">%</span>
        <Button size="sm" variant="primary" disabled={!changed} busy={busy} onClick={save}>
          Guardar
        </Button>
      </div>
      {error && <p className="mt-1 text-right text-xs text-bad">{error}</p>}
    </div>
  );
}

function PercentTable<T extends { id: number }>({
  path,
  field,
  title,
  description,
  rowLabel,
}: {
  path: string;
  field: "descuento" | "margen_minimo";
  title: string;
  description: string;
  rowLabel: (row: T) => string;
}) {
  const { data, loading, error, reload } = useApi<T[]>(path);
  return (
    <Card>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mb-3 mt-0.5 text-sm text-muted">{description}</p>
      <ErrorNotice message={error} />
      {loading && !data ? (
        <Loading />
      ) : (
        <ul className="divide-y divide-line">
          {data?.map((row) => (
            <li key={row.id} className="flex items-center justify-between gap-4 py-2.5">
              <span className="text-sm font-medium">{rowLabel(row)}</span>
              <PercentEditor
                key={String((row as Record<string, unknown>)[field])}
                fraction={String((row as Record<string, unknown>)[field])}
                label={`${title}: ${rowLabel(row)}`}
                onSave={async (fraction) => {
                  await api.put(`${path}/${row.id}`, { [field]: fraction });
                  await reload();
                }}
              />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// --- Promociones ----------------------------------------------------------------------

type PromoForm = { id: number | null; referencia: string; nombre: string; descuento: string; fecha_inicio: string; fecha_fin: string };

const today = () => new Date().toISOString().slice(0, 10);

export function promotionStatus(promo: Pick<Promotion, "fecha_inicio" | "fecha_fin">, date: string): "vigente" | "vencida" | "futura" {
  if (date > promo.fecha_fin) return "vencida";
  if (date < promo.fecha_inicio) return "futura";
  return "vigente";
}

const STATUS = {
  vigente: { label: "Vigente", tone: "ok" },
  vencida: { label: "Vencida", tone: "neutral" },
  futura: { label: "Futura", tone: "info" },
} as const;

function Promotions() {
  const { data, loading, error, reload } = useApi<Promotion[]>("/pricing/promociones");
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState<PromoForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const now = today();

  const visible = data?.filter((p) => !filter || p.referencia.includes(filter.trim().toUpperCase()) || p.nombre.toLowerCase().includes(filter.toLowerCase()));

  function edit(promo?: Promotion) {
    setFormError(null);
    setForm(
      promo
        ? { ...promo, descuento: fractionToPercentInput(promo.descuento) }
        : { id: null, referencia: "", nombre: "", descuento: "5", fecha_inicio: now, fecha_fin: now },
    );
  }

  async function save() {
    if (!form) return;
    setBusy(true);
    setFormError(null);
    const body = {
      referencia: form.referencia,
      nombre: form.nombre,
      descuento: percentInputToFraction(form.descuento),
      fecha_inicio: form.fecha_inicio,
      fecha_fin: form.fecha_fin,
    };
    try {
      if (form.id === null) await api.post("/pricing/promociones", body);
      else await api.put(`/pricing/promociones/${form.id}`, body);
      setForm(null);
      await reload();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(promo: Promotion) {
    if (!window.confirm(`¿Eliminar la promoción «${promo.nombre}» de ${promo.referencia}?`)) return;
    setListError(null);
    try {
      await api.delete(`/pricing/promociones/${promo.id}`);
      await reload();
    } catch (e) {
      setListError((e as Error).message);
    }
  }

  const set = (patch: Partial<PromoForm>) => setForm((f) => (f ? { ...f, ...patch } : f));

  return (
    <Card className="p-0">
      <div className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3">
        <div>
          <h2 className="text-base font-semibold">Promociones de fabricante</h2>
          <p className="mt-0.5 text-sm text-muted">Aplican solo dentro de su vigencia. No se permiten dos vigencias superpuestas para la misma referencia.</p>
        </div>
        <div className="flex items-center gap-2">
          <Input placeholder="Filtrar por referencia o nombre" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-64" aria-label="Filtrar promociones" />
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => edit()}>
            Nueva promoción
          </Button>
        </div>
      </div>
      <div className="px-5">
        <ErrorNotice message={error ?? listError} onClose={() => setListError(null)} />
      </div>
      {loading && !data ? (
        <Loading />
      ) : !visible?.length ? (
        <EmptyState title="Sin promociones">No hay promociones que coincidan.</EmptyState>
      ) : (
        <Table
          head={
            <tr>
              <th className={`${TH} pl-5`}>Referencia</th>
              <th className={TH}>Promoción</th>
              <th className={`${TH} text-right`}>Descuento</th>
              <th className={TH}>Vigencia</th>
              <th className={TH}>Estado</th>
              <th className={`${TH} pr-5`} />
            </tr>
          }
        >
          {visible.map((promo) => {
            const status = STATUS[promotionStatus(promo, now)];
            return (
              <tr key={promo.id}>
                <td className={`${TD} pl-5 font-semibold`}>{promo.referencia}</td>
                <td className={TD}>{promo.nombre}</td>
                <td className={`${TD} nums text-right`}>{formatPercent(promo.descuento)}</td>
                <td className={`${TD} text-muted`}>
                  {formatDate(promo.fecha_inicio)} – {formatDate(promo.fecha_fin)}
                </td>
                <td className={TD}>
                  <Badge tone={status.tone}>{status.label}</Badge>
                </td>
                <td className={`${TD} pr-5 text-right`}>
                  <button type="button" onClick={() => edit(promo)} aria-label={`Editar promoción de ${promo.referencia}`} className="rounded-full p-1.5 text-muted hover:bg-canvas hover:text-ink">
                    <Pencil className="size-4" />
                  </button>
                  <button type="button" onClick={() => remove(promo)} aria-label={`Eliminar promoción de ${promo.referencia}`} className="rounded-full p-1.5 text-muted hover:bg-red-50 hover:text-bad">
                    <Trash2 className="size-4" />
                  </button>
                </td>
              </tr>
            );
          })}
        </Table>
      )}

      {form && (
        <Modal
          title={form.id === null ? "Nueva promoción" : "Editar promoción"}
          onClose={() => setForm(null)}
          footer={
            <>
              <Button onClick={() => setForm(null)}>Cancelar</Button>
              <Button variant="primary" busy={busy} onClick={save}>
                Guardar
              </Button>
            </>
          }
        >
          <ErrorNotice message={formError} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Referencia" hint="Código exacto del catálogo.">
              <Input value={form.referencia} onChange={(e) => set({ referencia: e.target.value.toUpperCase() })} placeholder="POR-00001" />
            </Field>
            <Field label="Descuento (%)">
              <Input type="number" min={0.01} max={99.99} step={0.5} value={form.descuento} onChange={(e) => set({ descuento: e.target.value })} />
            </Field>
          </div>
          <Field label="Nombre">
            <Input value={form.nombre} onChange={(e) => set({ nombre: e.target.value })} placeholder="Promoción de fabricante" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Inicio">
              <Input type="date" value={form.fecha_inicio} onChange={(e) => set({ fecha_inicio: e.target.value })} />
            </Field>
            <Field label="Fin (inclusive)">
              <Input type="date" value={form.fecha_fin} onChange={(e) => set({ fecha_fin: e.target.value })} />
            </Field>
          </div>
        </Modal>
      )}
    </Card>
  );
}

// --- Parámetros de plazos y horario ---------------------------------------------------

function ParameterRow({ parameter, onSaved }: { parameter: Parameter; onSaved: () => Promise<void> }) {
  const [value, setValue] = useState(parameter.valor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.put(`/pricing/parametros/${parameter.clave}`, { valor: value });
      await onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0 flex-1">
        <p className="font-mono text-sm font-medium">{parameter.clave}</p>
        <p className="text-sm text-muted">{parameter.descripcion}</p>
        {error && <p className="mt-1 text-xs text-bad">{error}</p>}
      </div>
      <div className="flex items-center gap-2">
        <Input value={value} onChange={(e) => setValue(e.target.value)} aria-label={parameter.clave} className="w-44" />
        <Button size="sm" variant="primary" disabled={value.trim() === parameter.valor} busy={busy} onClick={save}>
          Guardar
        </Button>
      </div>
    </li>
  );
}

export function ParametersPanel() {
  const { data, loading, error, reload } = useApi<Parameter[]>("/pricing/parametros");
  return (
    <Card>
      <h2 className="text-base font-semibold">Plazos y horario hábil</h2>
      <p className="mb-2 mt-0.5 text-sm text-muted">
        Para una demostración, baje los plazos a pocos minutos y desactive el horario hábil. El intervalo del planificador se aplica al reiniciar la API.
      </p>
      <ErrorNotice message={error} />
      {loading && !data ? (
        <Loading />
      ) : (
        <ul className="divide-y divide-line">{data?.map((p) => <ParameterRow key={`${p.clave}:${p.valor}`} parameter={p} onSaved={reload} />)}</ul>
      )}
    </Card>
  );
}

// --- Página ---------------------------------------------------------------------------

const TABS = ["Promociones", "Reglas de precio", "Plazos"] as const;

export function Pricing() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Promociones");
  return (
    <>
      <PageHeader title="Reglas y promociones" subtitle="Los cambios aplican desde el siguiente cálculo; las cotizaciones emitidas conservan su precio." />
      <div className="mb-5 flex gap-1.5" role="tablist">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            className={`rounded-full px-4 py-2 text-sm font-medium ${tab === name ? "bg-brand-dark text-white" : "bg-surface text-muted shadow-card hover:text-ink"}`}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === "Promociones" && <Promotions />}
      {tab === "Reglas de precio" && (
        <div className="grid gap-5 lg:grid-cols-3">
          <PercentTable<Level> path="/pricing/niveles" field="descuento" title="Niveles de canal" description="Descuento según el nivel comercial del canal. Se acumula con los demás." rowLabel={(r) => r.nombre} />
          <PercentTable<VolumeTier>
            path="/pricing/escalas"
            field="descuento"
            title="Escala por volumen"
            description="Descuento por cantidad de la línea. No se acumula con la promoción: aplica el mayor."
            rowLabel={(r) => (r.cantidad_max === null ? `Desde ${r.cantidad_min} u` : `De ${r.cantidad_min} a ${r.cantidad_max} u`)}
          />
          <PercentTable<Margin> path="/pricing/margenes" field="margen_minimo" title="Margen mínimo por categoría" description="Por debajo de este margen la cotización requiere aprobación." rowLabel={(r) => r.categoria} />
        </div>
      )}
      {tab === "Plazos" && <ParametersPanel />}
    </>
  );
}

export function ParametersPage() {
  return (
    <>
      <PageHeader title="Parámetros" subtitle="Plazos del proceso y horario hábil de la operación." />
      <ParametersPanel />
    </>
  );
}
