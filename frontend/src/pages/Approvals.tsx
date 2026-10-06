import { Check, ClipboardCheck, Clock, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useUser } from "../auth/AuthContext";
import { LinesTable } from "../components/LinesTable";
import { Badge, Button, Card, EmptyState, ErrorNotice, Loading, Modal, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { formatDateTime, formatDuration, formatMoney, fractionToPercentInput } from "../lib/format";
import type { ApprovalQueueItem } from "../lib/types";
import { useApi } from "../lib/useApi";

type Decision = { item: ApprovalQueueItem; action: "aprobar" | "rechazar" };

function SlaBadge({ item }: { item: ApprovalQueueItem }) {
  if (item.sla_vencido) {
    return (
      <Badge tone="bad" icon={<Clock className="size-3" aria-hidden />}>
        SLA vencido
      </Badge>
    );
  }
  // Menos de 15 minutos: aviso de que está por vencer.
  const tone = item.sla_restante_segundos <= 15 * 60 ? "warn" : "ok";
  return (
    <Badge tone={tone} icon={<Clock className="size-3" aria-hidden />}>
      Quedan {formatDuration(item.sla_restante_segundos)}
    </Badge>
  );
}

export function Approvals() {
  const user = useUser();
  // La cola se refresca sola: el tiempo de SLA corre y llegan solicitudes nuevas.
  const { data, loading, error, reload } = useApi<ApprovalQueueItem[]>("/aprobaciones", 10_000);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const manager = user.rol === "gerente";

  function open(item: ApprovalQueueItem, action: Decision["action"]) {
    setDecision({ item, action });
    setComment("");
    setActionError(null);
  }

  async function confirm() {
    if (!decision) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.post(`/aprobaciones/${decision.item.id}/${decision.action}`, { comentario: comment });
      setDecision(null);
      await reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title={manager ? "Escalamientos" : "Cola de aprobaciones"}
        subtitle={
          manager
            ? "Solicitudes cuyo plazo de aprobación venció y fueron escaladas a gerencia."
            : "Descuentos que dejan el margen por debajo del mínimo. Más antiguas primero."
        }
      />
      <ErrorNotice message={error} />
      {loading && !data ? (
        <Loading />
      ) : !data?.length ? (
        <Card>
          <EmptyState icon={<ClipboardCheck className="size-6" />} title={manager ? "No hay solicitudes escaladas" : "No hay solicitudes pendientes"}>
            Cuando un ejecutivo solicite una aprobación, aparecerá aquí con todo su contexto.
          </EmptyState>
        </Card>
      ) : (
        <div className="space-y-5">
          {data.map((item) => {
            const q = item.cotizacion;
            return (
              <Card key={item.id}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/cotizaciones/${q.id}`} className="text-xl font-semibold text-brand hover:underline">
                        {q.numero}
                      </Link>
                      <SlaBadge item={item} />
                      {item.escalada && <Badge tone="bad">Escalada a gerencia</Badge>}
                    </div>
                    <p className="mt-1 text-sm text-muted">
                      {q.canal.nombre} · nivel {q.canal.nivel} · solicita {item.solicitante} · {formatDateTime(item.solicitada_en)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs uppercase tracking-wide text-muted">Total</p>
                    <p className="nums text-2xl font-semibold">{formatMoney(q.total)}</p>
                  </div>
                </div>

                <div className="mt-4">
                  <LinesTable
                    lines={q.lineas.map((line) => ({
                      referencia: line.referencia,
                      descripcion: line.descripcion ?? "",
                      cantidad: String(line.cantidad),
                      adicional: fractionToPercentInput(line.descuento_adicional),
                      result: line,
                    }))}
                  />
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
                  <p className="text-sm text-muted">Plazo: {formatDateTime(item.vence_en)}</p>
                  <div className="flex gap-2">
                    <Button variant="danger" icon={<X className="size-4" />} onClick={() => open(item, "rechazar")}>
                      Rechazar
                    </Button>
                    <Button variant="success" icon={<Check className="size-4" />} onClick={() => open(item, "aprobar")}>
                      Aprobar
                    </Button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {decision && (
        <Modal
          title={`${decision.action === "aprobar" ? "Aprobar" : "Rechazar"} ${decision.item.cotizacion.numero}`}
          onClose={() => setDecision(null)}
          footer={
            <>
              <Button onClick={() => setDecision(null)}>Cancelar</Button>
              <Button variant={decision.action === "aprobar" ? "success" : "danger"} busy={busy} disabled={!comment.trim()} onClick={confirm}>
                {decision.action === "aprobar" ? "Aprobar" : "Rechazar"}
              </Button>
            </>
          }
        >
          <ErrorNotice message={actionError} />
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Comentario (obligatorio)</span>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={4}
              autoFocus
              placeholder={decision.action === "aprobar" ? "Motivo de la autorización…" : "Qué debe ajustar el ejecutivo…"}
              className="w-full rounded-lg border border-line px-3 py-2 text-sm focus:border-brand focus:outline-2 focus:outline-brand/25"
            />
          </label>
          <p className="text-xs text-muted">El ejecutivo verá este comentario y queda en el historial de la cotización.</p>
        </Modal>
      )}
    </>
  );
}
