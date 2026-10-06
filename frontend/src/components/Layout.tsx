import { Bell, LogOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth, useUser } from "../auth/AuthContext";
import { api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { navFor, ROLE_LABEL } from "../lib/permissions";
import type { AppNotification, NotificationList } from "../lib/types";
import { useApi } from "../lib/useApi";

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="flex size-9 items-center justify-center rounded-xl bg-brand text-lg font-bold text-white shadow-sm">
        C<span className="text-accent">+</span>
      </span>
      <span className={`text-xl font-bold tracking-tight ${light ? "text-white" : "text-ink"}`}>
        COTIZA<span className="text-accent">+</span>
      </span>
    </span>
  );
}

/** Cierra un menú desplegable al hacer clic fuera o pulsar Escape. */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

function Notifications() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  // Se consultan cada 20 s: aprobaciones, escalamientos y seguimientos llegan solos.
  const { data, reload } = useApi<NotificationList>("/notificaciones", 20_000);
  const ref = useDismiss(open, () => setOpen(false));
  const unread = data?.no_leidas ?? 0;

  async function openItem(item: AppNotification) {
    setOpen(false);
    if (!item.leida) await api.post(`/notificaciones/${item.id}/leer`).catch(() => {});
    void reload();
    if (item.cotizacion_id) navigate(`/cotizaciones/${item.cotizacion_id}`);
  }

  async function markAll() {
    await api.post("/notificaciones/leer-todas").catch(() => {});
    void reload();
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={unread ? `Notificaciones: ${unread} sin leer` : "Notificaciones"}
        aria-expanded={open}
        className="relative flex size-10 items-center justify-center rounded-full bg-surface text-ink shadow-card hover:bg-canvas"
      >
        <Bell className="size-5" aria-hidden />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex min-w-5 items-center justify-center rounded-full bg-bad px-1 text-[11px] font-semibold leading-5 text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-96 max-w-[90vw] overflow-hidden rounded-2xl bg-surface shadow-2xl ring-1 ring-line">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <p className="font-semibold">Notificaciones</p>
            {unread > 0 && (
              <button type="button" onClick={markAll} className="text-xs font-medium text-brand hover:underline">
                Marcar todas como leídas
              </button>
            )}
          </div>
          <ul className="max-h-96 divide-y divide-line overflow-y-auto">
            {data?.items.length ? (
              data.items.map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => openItem(item)} className="flex w-full gap-3 px-4 py-3 text-left hover:bg-canvas">
                    <span className={`mt-1.5 size-2 shrink-0 rounded-full ${item.leida ? "bg-transparent" : "bg-brand"}`} aria-hidden />
                    <span className="min-w-0">
                      <span className={`block text-sm ${item.leida ? "text-muted" : "text-ink"}`}>{item.mensaje}</span>
                      <span className="mt-0.5 block text-xs text-muted">{formatDateTime(item.creada_en)}</span>
                    </span>
                  </button>
                </li>
              ))
            ) : (
              <li className="px-4 py-8 text-center text-sm text-muted">No tiene notificaciones.</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

export function Layout() {
  const user = useUser();
  const { logout } = useAuth();
  const initials = user.nombre
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-canvas/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-6 py-3">
          <Logo />
          <nav aria-label="Principal" className="flex flex-wrap items-center gap-1.5">
            {navFor(user.rol).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                    isActive ? "bg-surface text-ink shadow-card" : "text-muted hover:bg-surface/70 hover:text-ink"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <Notifications />
            <div className="flex items-center gap-2 rounded-full bg-surface py-1 pl-1 pr-3 shadow-card">
              <span className="flex size-8 items-center justify-center rounded-full bg-brand-dark text-xs font-semibold text-white" aria-hidden>
                {initials}
              </span>
              <span className="leading-tight">
                <span className="block text-sm font-medium text-ink">{user.nombre}</span>
                <span className="block text-[11px] text-muted">{ROLE_LABEL[user.rol]}</span>
              </span>
            </div>
            <button
              type="button"
              onClick={logout}
              aria-label="Cerrar sesión"
              title="Cerrar sesión"
              className="flex size-10 items-center justify-center rounded-full bg-surface text-muted shadow-card hover:bg-canvas hover:text-ink"
            >
              <LogOut className="size-5" aria-hidden />
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
