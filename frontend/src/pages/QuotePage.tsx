import { ArrowLeft, ArrowRight, Calculator, CopyPlus, Download, FileCheck2, Send, ThumbsDown, Trophy } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useUser } from "../auth/AuthContext";
import { CatalogBrowser } from "../components/CatalogBrowser";
import { LinesTable, type ViewLine } from "../components/LinesTable";
import { ProductSearch } from "../components/ProductSearch";
import { QuoteHistory } from "../components/QuoteHistory";
import { Badge, Button, Card, EmptyState, ErrorNotice, Field, Input, Loading, Notice, SectionTitle, Select, StateBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatDateTime, formatMoney, fractionToPercentInput, percentInputToFraction, toLocalInput } from "../lib/format";
import { quoteActions } from "../lib/permissions";
import type { Channel, Product, Quote } from "../lib/types";
import { useApi } from "../lib/useApi";

interface Draft {
  canalId: string;
  recibida: string; // valor de un campo datetime-local
  lines: ViewLine[];
}

function draftFromQuote(quote: Quote): Draft {
  return {
    canalId: String(quote.canal.id),
    recibida: toLocalInput(new Date(quote.recibida_en)),
    lines: quote.lineas.map((line) => ({
      referencia: line.referencia,
      descripcion: line.descripcion ?? "",
      cantidad: String(line.cantidad),
      adicional: fractionToPercentInput(line.descuento_adicional),
      result: line.estado ? line : undefined,
    })),
  };
}

/** Lo que define el cálculo: si cambia respecto a lo guardado, hay que recalcular. */
function signature(draft: Draft): string {
  return JSON.stringify([
    draft.canalId,
    draft.recibida,
    draft.lines.map((l) => [l.referencia, Number(l.cantidad), percentInputToFraction(l.adicional)]),
  ]);
}

function validate(draft: Draft): string | null {
  if (!draft.canalId) return "Seleccione el canal.";
  if (!draft.recibida) return "Indique la hora en que se recibió la solicitud.";
  if (new Date(draft.recibida) > new Date()) return "La hora de recepción no puede estar en el futuro.";
  if (draft.lines.length === 0) return "Agregue al menos una referencia.";
  for (const line of draft.lines) {
    const quantity = Number(line.cantidad);
    if (!Number.isInteger(quantity) || quantity <= 0) return `La cantidad de ${line.referencia} debe ser un entero mayor que cero.`;
    const extra = Number(line.adicional.replace(",", ".") || "0");
    if (!(extra >= 0 && extra < 100)) return `El descuento adicional de ${line.referencia} debe estar entre 0 % y menos de 100 %.`;
  }
  return null;
}

export function QuotePage() {
  const { id } = useParams();
  const isNew = id === "nueva";
  const user = useUser();
  const navigate = useNavigate();

  const channels = useApi<Channel[]>(user.rol === "ejecutivo" ? "/canales" : null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [draft, setDraft] = useState<Draft>({ canalId: "", recibida: toLocalInput(new Date()), lines: [] });
  const [loading, setLoading] = useState(!isNew);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [version, setVersion] = useState(0); // cambia tras cada acción: refresca el historial

  // Id de la cotización que ya está en pantalla, para no volver a pedirla al cambiar la URL.
  const shownId = useRef<number | null>(null);

  const apply = useCallback((next: Quote) => {
    shownId.current = next.id;
    setQuote(next);
    setDraft(draftFromQuote(next));
    setVersion((v) => v + 1);
  }, []);

  const load = useCallback(async () => {
    if (isNew) return;
    try {
      apply(await api.get<Quote>(`/cotizaciones/${id}`));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [apply, id, isNew]);

  useEffect(() => {
    if (isNew) {
      shownId.current = null;
      setQuote(null);
      setDraft({ canalId: "", recibida: toLocalInput(new Date()), lines: [] });
      setLoading(false);
    } else if (shownId.current !== Number(id)) {
      setLoading(true);
      void load();
    }
  }, [id, isNew, load]);

  // Mientras espera aprobación, la decisión llega sola: se consulta cada 10 s.
  const waiting = quote?.estado === "PENDIENTE_APROBACION" && quote.aprobacion?.estado === "PENDIENTE";
  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(() => void load(), 10_000);
    return () => clearInterval(timer);
  }, [waiting, load]);

  const dirty = useMemo(() => (quote ? signature(draft) !== signature(draftFromQuote(quote)) : true), [draft, quote]);
  const actions = quote ? quoteActions(quote, user, dirty) : null;
  const editable = isNew || Boolean(actions?.edit);
  const calculated = Boolean(quote?.evaluacion) && !dirty;

  async function run(name: string, action: () => Promise<void>) {
    setBusy(name);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  function body() {
    return {
      canal_id: Number(draft.canalId),
      recibida_en: new Date(draft.recibida).toISOString(),
      lineas: draft.lines.map((l) => ({
        referencia: l.referencia,
        cantidad: Number(l.cantidad),
        descuento_adicional: percentInputToFraction(l.adicional),
      })),
    };
  }

  /** Guarda lo escrito (crea o actualiza) y calcula, en un solo paso. */
  const calculate = () =>
    run("calcular", async () => {
      const problem = validate(draft);
      if (problem) throw new Error(problem);
      let current = quote;
      if (!current) current = await api.post<Quote>("/cotizaciones", body());
      else if (dirty) current = await api.put<Quote>(`/cotizaciones/${current.id}`, body());
      const result = await api.post<Quote>(`/cotizaciones/${current.id}/calcular`);
      apply(result);
      if (isNew) navigate(`/cotizaciones/${result.id}`, { replace: true });
    });

  const post = (name: string, path: string, payload?: unknown) =>
    run(name, async () => apply(await api.post<Quote>(`/cotizaciones/${quote!.id}/${path}`, payload)));

  const newVersion = () =>
    run("version", async () => {
      const created = await api.post<Quote>(`/cotizaciones/${quote!.id}/nueva-version`);
      navigate(`/cotizaciones/${created.id}`);
    });

  function addProduct(product: Product) {
    setDraft((d) => ({
      ...d,
      lines: [...d.lines, { referencia: product.referencia, descripcion: product.descripcion, cantidad: "1", adicional: "0" }],
    }));
  }

  if (loading) return <Loading />;
  if (!isNew && !quote) return <ErrorNotice message={error ?? "No se encontró la cotización."} />;

  const title = quote ? `${quote.numero}${quote.version > 1 ? ` · v${quote.version}` : ""}` : "Nueva cotización";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/cotizaciones" aria-label="Volver a cotizaciones" className="flex size-10 items-center justify-center rounded-full bg-surface text-muted shadow-card hover:text-ink">
            <ArrowLeft className="size-5" />
          </Link>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
              {quote && <StateBadge state={quote.estado} replaced={quote.reemplazada} />}
            </div>
            {quote && (
              <p className="mt-0.5 text-sm text-muted">
                {quote.canal.nombre} · nivel {quote.canal.nivel} · {quote.ejecutivo.nombre}
              </p>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {actions?.downloadPdf && (
            <Button icon={<Download className="size-4" />} busy={busy === "pdf"} onClick={() => run("pdf", () => api.download(`/cotizaciones/${quote!.id}/pdf`, `${quote!.numero}.pdf`))}>
              Descargar PDF
            </Button>
          )}
          {actions?.newVersion && (
            <Button icon={<CopyPlus className="size-4" />} busy={busy === "version"} onClick={newVersion}>
              Nueva versión
            </Button>
          )}
          {actions?.lose && (
            <Button icon={<ThumbsDown className="size-4" />} busy={busy === "perdida"} onClick={() => post("perdida", "cerrar", { resultado: "PERDIDA" })}>
              Marcar perdida
            </Button>
          )}
          {actions?.win && (
            <Button variant="success" icon={<Trophy className="size-4" />} busy={busy === "ganada"} onClick={() => post("ganada", "cerrar", { resultado: "GANADA" })}>
              Marcar ganada
            </Button>
          )}
        </div>
      </div>

      <ErrorNotice message={error} onClose={() => setError(null)} />
      {quote?.reemplazada && (
        <Notice
          tone="info"
          title="Esta versión fue reemplazada"
          action={
            quote.version_siguiente_id && (
              <Button variant="primary" size="sm" className="self-center" icon={<ArrowRight className="size-4" />} onClick={() => navigate(`/cotizaciones/${quote.version_siguiente_id}`)}>
                Ir a la orden actualizada
              </Button>
            )
          }
        >
          Conserva los precios con los que se emitió, pero ya no está vigente ni compromete inventario.
        </Notice>
      )}
      {quote && <ApprovalStatus quote={quote} />}

      {/* Editable: catálogo y líneas lado a lado, datos e historial debajo. En lectura: líneas y columna lateral. */}
      <div className={editable ? "space-y-5" : "grid gap-5 xl:grid-cols-[1fr_340px]"}>
        <div className="space-y-5">
          {editable && (
            <Card>
              <SectionTitle>Solicitud del canal</SectionTitle>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Canal">
                  <Select value={draft.canalId} onChange={(e) => setDraft((d) => ({ ...d, canalId: e.target.value }))}>
                    <option value="">Seleccione un canal…</option>
                    {channels.data?.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.nombre} — {c.nivel}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Hora de recepción de la solicitud" hint="Cuándo pidió el canal la cotización; mide el tiempo de respuesta.">
                  <Input type="datetime-local" value={draft.recibida} max={toLocalInput(new Date())} onChange={(e) => setDraft((d) => ({ ...d, recibida: e.target.value }))} />
                </Field>
              </div>
            </Card>
          )}

          <div className={editable ? "grid items-start gap-5 xl:grid-cols-[380px_minmax(0,1fr)]" : undefined}>
          {editable && (
            // Fijo bajo la cabecera: sigue a la vista aunque la lista de líneas crezca.
            <Card className="xl:sticky xl:top-20">
              <SectionTitle>Catálogo de productos</SectionTitle>
              <CatalogBrowser onSelect={addProduct} exclude={draft.lines.map((l) => l.referencia)} />
            </Card>
          )}

          <Card className="min-w-0">
            <SectionTitle aside={quote?.total != null && !dirty && <span className="nums text-2xl font-semibold">{formatMoney(quote.total)}</span>}>
              Líneas
            </SectionTitle>
            {editable && (
              <div className="mb-4">
                <ProductSearch onSelect={addProduct} exclude={draft.lines.map((l) => l.referencia)} autoFocus={isNew} />
              </div>
            )}
            {draft.lines.length === 0 ? (
              <EmptyState title="Aún no hay líneas">Elija una referencia del catálogo o búsquela por código o descripción.</EmptyState>
            ) : (
              <LinesTable
                lines={draft.lines}
                editable={editable}
                stale={dirty && Boolean(quote?.evaluacion)}
                onChange={(index, patch) => setDraft((d) => ({ ...d, lines: d.lines.map((l, i) => (i === index ? { ...l, ...patch } : l)) }))}
                onRemove={(index) => setDraft((d) => ({ ...d, lines: d.lines.filter((_, i) => i !== index) }))}
              />
            )}

            {editable && (
              <div className="mt-5 space-y-3 border-t border-line pt-4">
                {calculated && quote && <EvaluationNotice quote={quote} />}
                {dirty && quote?.evaluacion && (
                  <Notice tone="info">Hay cambios sin calcular. Calcule de nuevo para ver el precio y poder emitir.</Notice>
                )}
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Button variant={calculated ? "secondary" : "primary"} icon={<Calculator className="size-4" />} busy={busy === "calcular"} onClick={calculate}>
                    {calculated ? "Recalcular" : "Calcular"}
                  </Button>
                  {quote?.evaluacion === "REQUIERE_APROBACION" && (
                    <Button
                      variant="primary"
                      icon={<Send className="size-4" />}
                      disabled={!actions?.requestApproval}
                      busy={busy === "aprobacion"}
                      onClick={() => post("aprobacion", "solicitar-aprobacion")}
                    >
                      Solicitar aprobación
                    </Button>
                  )}
                  <Button
                    variant="success"
                    icon={<FileCheck2 className="size-4" />}
                    disabled={!actions?.issue}
                    title={actions?.issue ? undefined : "Disponible cuando la cotización esté calculada y lista para emitir"}
                    busy={busy === "emitir"}
                    onClick={() => post("emitir", "emitir")}
                  >
                    Emitir
                  </Button>
                </div>
              </div>
            )}

            {!editable && actions?.issue && (
              <div className="mt-5 flex justify-end border-t border-line pt-4">
                <Button variant="success" icon={<FileCheck2 className="size-4" />} busy={busy === "emitir"} onClick={() => post("emitir", "emitir")}>
                  Confirmar emisión
                </Button>
              </div>
            )}
          </Card>
          </div>
        </div>

        {quote && (
          <div className={editable ? "grid items-start gap-5 md:grid-cols-2" : "space-y-5"}>
            <Card>
              <SectionTitle>Datos</SectionTitle>
              <dl className="space-y-2 text-sm">
                <Row label="Recibida">{formatDateTime(quote.recibida_en)}</Row>
                <Row label="Creada">{formatDateTime(quote.creada_en)}</Row>
                {quote.emitida_en && <Row label="Emitida">{formatDateTime(quote.emitida_en)}</Row>}
                {quote.vigente_hasta && <Row label="Vigente hasta">{formatDateTime(quote.vigente_hasta)}</Row>}
                {quote.cerrada_en && <Row label="Cerrada">{formatDateTime(quote.cerrada_en)}</Row>}
                {quote.version_anterior_id && (
                  <Row label="Versión anterior">
                    <Link to={`/cotizaciones/${quote.version_anterior_id}`} className="font-medium text-brand hover:underline">
                      Ver v{quote.version - 1}
                    </Link>
                  </Row>
                )}
              </dl>
            </Card>
            <Card>
              <SectionTitle>Historial</SectionTitle>
              <QuoteHistory quoteId={quote.id} refreshKey={version} />
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right text-ink">{children}</dd>
    </div>
  );
}

/** Resultado del cálculo y qué sigue. */
function EvaluationNotice({ quote }: { quote: Quote }) {
  if (quote.evaluacion === "LISTA_PARA_EMITIR") {
    const backorder = quote.lineas.filter((l) => l.bajo_pedido).length;
    return (
      <Notice tone="ok" title="Lista para emitir">
        Todas las líneas cumplen el margen mínimo.
        {backorder > 0 && ` ${backorder === 1 ? "Una línea queda" : `${backorder} líneas quedan`} bajo pedido; no impide la emisión.`}
      </Notice>
    );
  }
  if (quote.evaluacion === "REQUIERE_APROBACION") {
    return (
      <Notice tone="warn" title="Requiere aprobación">
        El margen de alguna línea queda por debajo del mínimo de su categoría. La emisión está bloqueada hasta que un aprobador la autorice.
      </Notice>
    );
  }
  return (
    <Notice tone="bad" title="No se puede emitir">
      Hay líneas no cotizables o con precio por debajo del costo. Corríjalas o retírelas; no se pueden enviar a aprobación.
    </Notice>
  );
}

/** Estado de la última solicitud de aprobación, con el comentario de quien decidió. */
function ApprovalStatus({ quote }: { quote: Quote }) {
  const approval = quote.aprobacion;
  if (!approval) return null;
  if (approval.estado === "PENDIENTE" && quote.estado === "PENDIENTE_APROBACION") {
    return (
      <Notice tone="warn" title="En cola de aprobación">
        Solicitada el {formatDateTime(approval.solicitada_en)}. El plazo vence el {formatDateTime(approval.vence_en)}.{" "}
        {approval.escalada && <Badge tone="bad">Escalada a gerencia</Badge>}
      </Notice>
    );
  }
  if (approval.estado === "APROBADA" && quote.estado === "PENDIENTE_APROBACION") {
    return (
      <Notice tone="ok" title={`Aprobada por ${approval.resuelta_por ?? "el aprobador"}`}>
        «{approval.comentario}». Ya puede confirmar la emisión.
      </Notice>
    );
  }
  if (approval.estado === "RECHAZADA" && (quote.estado === "CALCULADA" || quote.estado === "BORRADOR")) {
    return (
      <Notice tone="bad" title={`Rechazada por ${approval.resuelta_por ?? "el aprobador"}`}>
        «{approval.comentario}». Ajuste el descuento y vuelva a calcular.
      </Notice>
    );
  }
  return null;
}
