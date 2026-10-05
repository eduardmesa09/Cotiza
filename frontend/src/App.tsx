import { useEffect, useState } from "react";

type ApiStatus = "consultando" | "disponible" | "no disponible";

// Página provisional de la Fase 1: confirma que el frontend llega a la API a través de Nginx.
// Las pantallas del producto se construyen en la Fase 6.
export default function App() {
  const [status, setStatus] = useState<ApiStatus>("consultando");

  useEffect(() => {
    fetch("/api/health")
      .then((response) => setStatus(response.ok ? "disponible" : "no disponible"))
      .catch(() => setStatus("no disponible"));
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h1 className="text-3xl font-bold text-slate-900">COTIZA+</h1>
        <p className="mt-2 text-slate-600">Cotización automatizada a canales de distribución</p>
        <p className="mt-6 text-sm text-slate-500">
          API:{" "}
          <span className={status === "disponible" ? "font-semibold text-emerald-600" : "font-semibold text-amber-600"}>
            {status}
          </span>
        </p>
      </div>
    </main>
  );
}
