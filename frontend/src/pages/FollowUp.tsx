import { CalendarClock, PhoneCall, ThumbsDown, Trophy } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button, Card, EmptyState, ErrorNotice, Input, Loading, PageHeader, StateBadge } from "../components/ui";
import { api } from "../lib/api";
import { formatDateTime, formatMoney } from "../lib/format";
import type { FollowUpTask } from "../lib/types";
import { useApi } from "../lib/useApi";

type Action = "GANADA" | "PERDIDA" | "MANTENER";

export function FollowUp() {
  const { data, loading, error, reload } = useApi<FollowUpTask[]>("/seguimiento", 20_000);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function resolve(task: FollowUpTask, accion: Action) {
    setBusy(`${task.id}-${accion}`);
    setActionError(null);
    try {
      await api.post(`/seguimiento/${task.id}/resolver`, { accion, nota: notes[task.id]?.trim() || null });
      await reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title="Tareas de seguimiento" subtitle="Cotizaciones emitidas que siguen sin respuesta del canal." />
      <ErrorNotice message={error ?? actionError} onClose={() => setActionError(null)} />
      {loading && !data ? (
        <Loading />
      ) : !data?.length ? (
        <Card>
          <EmptyState icon={<PhoneCall className="size-6" />} title="No tiene seguimientos pendientes">
            El sistema crea una tarea cuando una cotización emitida lleva 48 horas sin cierre.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {data.map((task) => {
            const q = task.cotizacion;
            return (
              <Card key={task.id}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/cotizaciones/${q.id}`} className="text-xl font-semibold text-brand hover:underline">
                        {q.numero}
                      </Link>
                      <StateBadge state={q.estado} />
                    </div>
                    <p className="mt-1 text-sm text-ink">{q.canal.nombre}</p>
                  </div>
                  <p className="nums text-xl font-semibold">{formatMoney(q.total)}</p>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <dt className="text-xs text-muted">Emitida</dt>
                    <dd>{formatDateTime(q.emitida_en)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Vigente hasta</dt>
                    <dd>{formatDateTime(q.vigente_hasta)}</dd>
                  </div>
                </dl>
                <div className="mt-4">
                  <Input
                    placeholder="Nota del contacto con el canal (opcional)"
                    aria-label={`Nota de seguimiento de ${q.numero}`}
                    value={notes[task.id] ?? ""}
                    onChange={(e) => setNotes((n) => ({ ...n, [task.id]: e.target.value }))}
                  />
                </div>
                <div className="mt-3 flex flex-wrap justify-end gap-2">
                  <Button icon={<CalendarClock className="size-4" />} busy={busy === `${task.id}-MANTENER`} onClick={() => resolve(task, "MANTENER")}>
                    Mantener en seguimiento
                  </Button>
                  <Button variant="danger" icon={<ThumbsDown className="size-4" />} busy={busy === `${task.id}-PERDIDA`} onClick={() => resolve(task, "PERDIDA")}>
                    Perdida
                  </Button>
                  <Button variant="success" icon={<Trophy className="size-4" />} busy={busy === `${task.id}-GANADA`} onClick={() => resolve(task, "GANADA")}>
                    Ganada
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
