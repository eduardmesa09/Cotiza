// Utilidades de prueba: una API simulada sobre `fetch` y datos de ejemplo.

import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../auth/AuthContext";
import { setToken } from "../lib/api";
import type { Kpi, Quote, QuoteLine, Role, User } from "../lib/types";

type Handler = unknown | ((body: unknown) => unknown);

export class HttpError {
  constructor(
    public status: number,
    public detail: string,
  ) {}
}

/** Sustituye `fetch`. Las rutas se indican como "GET /cotizaciones/7"; la consulta (?a=b) se ignora
 *  al buscar. Devuelve la lista de llamadas hechas, para verificarlas. */
export function mockApi(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = url.replace(/^\/api/, "").split("?")[0];
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path, body });
    const handler = routes[`${method} ${path}`];
    if (handler === undefined) {
      return { ok: false, status: 404, json: async () => ({ detail: `Ruta no simulada: ${method} ${path}` }), headers: new Headers() };
    }
    const result = typeof handler === "function" ? (handler as (b: unknown) => unknown)(body) : handler;
    if (result instanceof HttpError) {
      return { ok: false, status: result.status, json: async () => ({ detail: result.detail }), headers: new Headers() };
    }
    return { ok: true, status: 200, json: async () => result, headers: new Headers() };
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export function userOf(rol: Role, id = 1): User {
  return { id, usuario: rol, nombre: `Usuario ${rol}`, rol };
}

/** Monta un componente con sesión iniciada y enrutador. Requiere que `mockApi` incluya "GET /auth/me". */
export function renderApp(ui: ReactElement, route = "/") {
  setToken("token-de-prueba");
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  );
}

export function line(overrides: Partial<QuoteLine> = {}): QuoteLine {
  return {
    referencia: "POR-DEMO01",
    cantidad: 20,
    descuento_adicional: "0.0000",
    descripcion: "Portátil empresarial (demo)",
    categoria: "Portátiles",
    estado: "OK",
    costo: "620.00",
    precio_lista: "800.00",
    precio_unitario: "729.60",
    total: "14592.00",
    margen: "0.1502",
    margen_minimo: "0.0800",
    requiere_aprobacion: false,
    bajo_pedido: false,
    disponible: 150,
    cantidad_comprometida: 0,
    promocion_fin: "2026-11-04",
    reglas_aplicadas: [
      { regla: "RN-01", descripcion: "Precio de lista vigente", valor: null, precio_resultante: "800.00" },
      { regla: "RN-02", descripcion: "Descuento por nivel Plata (4 %)", valor: "0.04", precio_resultante: "768.00" },
      { regla: "RN-04", descripcion: "Promoción vigente 'Promo' (5 %)", valor: "0.05", precio_resultante: "729.60" },
    ],
    ...overrides,
  };
}

export function quote(overrides: Partial<Quote> = {}): Quote {
  return {
    id: 7,
    numero: "COT-000007",
    version: 1,
    estado: "CALCULADA",
    evaluacion: "LISTA_PARA_EMITIR",
    total: "14592.00",
    canal: { id: 3, nombre: "Soluciones Andinas TI S.A.S. (demo)", nivel: "Plata" },
    ejecutivo: { id: 1, nombre: "Camila Torres", nivel: null },
    recibida_en: "2026-10-05T14:30:00Z",
    creada_en: "2026-10-05T15:00:00Z",
    calculada_en: "2026-10-05T15:02:00Z",
    emitida_en: null,
    vigente_hasta: null,
    cerrada_en: null,
    reemplazada: false,
    lineas_count: 1,
    lineas: [line()],
    acciones_permitidas: ["CALCULAR", "EDITAR", "EMITIR"],
    puede_crear_version: false,
    tiene_pdf: false,
    version_anterior_id: null,
    aprobacion: null,
    ...overrides,
  };
}

export function kpi(overrides: Partial<Kpi> = {}): Kpi {
  return {
    codigo: "K3",
    nombre: "Tiempo de respuesta al canal",
    valor: 1.6,
    unidad: "h",
    linea_base: 6.4,
    meta: 1.5,
    sentido: "menor",
    muestra: 12,
    formula: "Promedio de (emisión − recepción), en horas hábiles",
    ...overrides,
  };
}
