import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "./App";
import { getToken, setToken } from "./lib/api";
import { HttpError, kpi, line, mockApi, quote, renderApp, userOf } from "./test/helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

const EMPTY_NOTIFICATIONS = { no_leidas: 0, items: [] };
const CHANNELS = [{ id: 3, nit: "900123456-7", nombre: "Soluciones Andinas TI S.A.S. (demo)", nivel: "Plata", ciudad: "Bogotá" }];

/** Rutas comunes de una sesión iniciada con el rol dado. */
function session(rol: Parameters<typeof userOf>[0], extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /auth/me": userOf(rol),
    "GET /notificaciones": EMPTY_NOTIFICATIONS,
    "GET /cotizaciones": [],
    "GET /canales": CHANNELS,
    ...extra,
  });
}

describe("inicio de sesión", () => {
  it("sin sesión, cualquier ruta lleva al inicio de sesión", async () => {
    mockApi({});
    renderApp(<AppRoutes />, "/cotizaciones");
    setToken(null);
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
  });

  it("al ingresar guarda el token y lleva a la pantalla principal del rol", async () => {
    setToken(null);
    mockApi({
      "POST /auth/login": { access_token: "abc", token_type: "bearer", usuario: userOf("aprobador") },
      "GET /notificaciones": EMPTY_NOTIFICATIONS,
      "GET /aprobaciones": [],
    });
    const { unmount } = renderApp(<AppRoutes />, "/login");
    setToken(null);
    unmount();
    renderLogin();

    await userEvent.type(screen.getByLabelText("Usuario"), "aprobador");
    await userEvent.type(screen.getByLabelText("Contraseña"), "Cotiza2026*");
    await userEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    expect(await screen.findByRole("heading", { name: "Cola de aprobaciones" })).toBeInTheDocument();
    expect(getToken()).toBe("abc");
  });

  it("muestra el error cuando las credenciales no son válidas", async () => {
    mockApi({ "POST /auth/login": new HttpError(401, "Usuario o contraseña incorrectos") });
    renderLogin();
    await userEvent.type(screen.getByLabelText("Usuario"), "ejecutivo");
    await userEvent.type(screen.getByLabelText("Contraseña"), "mala");
    await userEvent.click(screen.getByRole("button", { name: "Ingresar" }));
    expect(await screen.findByText("Usuario o contraseña incorrectos")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });

  it("si el token guardado ya no sirve, vuelve al inicio de sesión", async () => {
    mockApi({ "GET /auth/me": new HttpError(401, "Sesión inválida o expirada") });
    renderApp(<AppRoutes />, "/cotizaciones");
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });
});

/** Monta la aplicación en /login sin token guardado. */
function renderLogin() {
  const view = renderApp(<AppRoutes />, "/login");
  return view;
}

describe("acceso por rol", () => {
  it("el ejecutivo ve su menú y el botón de nueva cotización", async () => {
    session("ejecutivo");
    renderApp(<AppRoutes />, "/");
    expect(await screen.findByRole("heading", { name: "Mis cotizaciones" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Mis cotizaciones", "Seguimiento", "Indicadores"]);
    expect(screen.getByRole("link", { name: /nueva cotización/i })).toBeInTheDocument();
  });

  it("un rol sin permiso para una ruta es llevado a su pantalla principal", async () => {
    session("ejecutivo");
    renderApp(<AppRoutes />, "/usuarios");
    expect(await screen.findByRole("heading", { name: "Mis cotizaciones" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Usuarios" })).not.toBeInTheDocument();
  });

  it("el aprobador consulta cotizaciones pero no puede crear", async () => {
    session("aprobador", { "GET /aprobaciones": [] });
    renderApp(<AppRoutes />, "/cotizaciones/nueva");
    expect(await screen.findByRole("heading", { name: "Cola de aprobaciones" })).toBeInTheDocument();
  });

  it("el administrador solo gestiona usuarios y parámetros", async () => {
    session("admin", { "GET /usuarios": [] });
    renderApp(<AppRoutes />, "/tablero");
    expect(await screen.findByRole("heading", { name: "Usuarios" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Principal" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Usuarios", "Parámetros"]);
  });
});

describe("cotización: cuándo se puede emitir", () => {
  const open = (q: ReturnType<typeof quote>, extra: Record<string, unknown> = {}) => {
    const calls = session("ejecutivo", { "GET /cotizaciones/7": q, "GET /cotizaciones/7/eventos": [], ...extra });
    renderApp(<AppRoutes />, "/cotizaciones/7");
    return calls;
  };
  const emitir = () => screen.getByRole("button", { name: "Emitir" });

  it("lista para emitir: el botón está habilitado y emite", async () => {
    const issued = quote({ estado: "EMITIDA", acciones_permitidas: ["GANAR", "INICIAR_SEGUIMIENTO", "VENCER"], tiene_pdf: true, puede_crear_version: true });
    const calls = open(quote(), { "POST /cotizaciones/7/emitir": issued });
    expect(await screen.findByText("Lista para emitir")).toBeInTheDocument();
    expect(emitir()).toBeEnabled();

    await userEvent.click(emitir());

    expect(await screen.findByRole("button", { name: /descargar pdf/i })).toBeInTheDocument();
    expect(screen.getByText("Emitida")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/cotizaciones/7/emitir")).toBe(true);
    // Una emitida ya no se edita: desaparecen los campos y el botón de calcular.
    expect(screen.queryByRole("button", { name: /calcular/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("requiere aprobación: emitir deshabilitado y se ofrece solicitar aprobación", async () => {
    const needs = quote({
      evaluacion: "REQUIERE_APROBACION",
      acciones_permitidas: ["CALCULAR", "EDITAR", "SOLICITAR_APROBACION"],
      lineas: [line({ descuento_adicional: "0.0900", precio_unitario: "663.94", margen: "0.0662", requiere_aprobacion: true })],
    });
    open(needs);
    expect(await screen.findByText(/La emisión está bloqueada/)).toBeInTheDocument();
    expect(emitir()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Solicitar aprobación" })).toBeEnabled();
    expect(screen.getAllByText("Requiere aprobación").length).toBeGreaterThan(0);
  });

  it("precio bajo el costo: ni emitir ni solicitar aprobación", async () => {
    const blocked = quote({
      evaluacion: "NO_EMITIBLE",
      acciones_permitidas: ["CALCULAR", "EDITAR"],
      lineas: [line({ estado: "BAJO_COSTO", precio_unitario: "583.68", margen: "-0.0622", requiere_aprobacion: true })],
    });
    open(blocked);
    expect(await screen.findByText("No se puede emitir")).toBeInTheDocument();
    expect(emitir()).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Solicitar aprobación" })).not.toBeInTheDocument();
    expect(screen.getByText("Bajo costo")).toBeInTheDocument();
  });

  it("al cambiar una cantidad, emitir se deshabilita hasta recalcular", async () => {
    open(quote());
    await screen.findByText("Lista para emitir");
    expect(emitir()).toBeEnabled();

    await userEvent.type(screen.getByLabelText("Cantidad de POR-DEMO01"), "0");

    expect(emitir()).toBeDisabled();
    expect(screen.getByText(/Hay cambios sin calcular/)).toBeInTheDocument();
    expect(screen.queryByText("Lista para emitir")).not.toBeInTheDocument();
  });

  it("recalcular guarda los cambios y vuelve a habilitar la emisión", async () => {
    const recalculated = quote({ total: "145920.00", lineas: [line({ cantidad: 200, total: "145920.00" })] });
    const calls = open(quote(), { "PUT /cotizaciones/7": recalculated, "POST /cotizaciones/7/calcular": recalculated });
    await screen.findByText("Lista para emitir");
    await userEvent.type(screen.getByLabelText("Cantidad de POR-DEMO01"), "0");

    await userEvent.click(screen.getByRole("button", { name: "Calcular" }));

    await waitFor(() => expect(emitir()).toBeEnabled());
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.body).toMatchObject({ canal_id: 3, lineas: [{ referencia: "POR-DEMO01", cantidad: 200, descuento_adicional: "0.0000" }] });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toContain("POST /cotizaciones/7/calcular");
  });

  it("pendiente y aprobada: el ejecutivo confirma la emisión, sin poder editar", async () => {
    const approved = quote({
      estado: "PENDIENTE_APROBACION",
      evaluacion: "REQUIERE_APROBACION",
      acciones_permitidas: ["EMITIR"],
      aprobacion: { id: 1, estado: "APROBADA", solicitada_en: "2026-10-05T15:10:00Z", vence_en: "2026-10-05T16:10:00Z", escalada: false, resuelta_en: "2026-10-05T15:30:00Z", resuelta_por: "Andrés Pardo", comentario: "Cliente estratégico" },
    });
    open(approved);
    expect(await screen.findByText("Aprobada por Andrés Pardo")).toBeInTheDocument();
    expect(screen.getByText(/Cliente estratégico/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmar emisión" })).toBeEnabled();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("otro rol ve la cotización en modo lectura", async () => {
    mockApi({
      "GET /auth/me": userOf("gerente", 3),
      "GET /notificaciones": EMPTY_NOTIFICATIONS,
      "GET /cotizaciones/7": quote(),
      "GET /cotizaciones/7/eventos": [],
    });
    renderApp(<AppRoutes />, "/cotizaciones/7");
    expect(await screen.findByRole("heading", { name: "COT-000007" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Emitir" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /calcular/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });
});

describe("nueva cotización", () => {
  it("valida antes de calcular y no llama a la API si falta el canal", async () => {
    const calls = session("ejecutivo");
    renderApp(<AppRoutes />, "/cotizaciones/nueva");
    expect(await screen.findByRole("heading", { name: "Nueva cotización" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Emitir" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Calcular" }));

    expect(await screen.findByText("Seleccione el canal.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("busca una referencia, la agrega, crea la cotización y la calcula", async () => {
    const calculated = quote();
    const calls = session("ejecutivo", {
      "GET /catalogo": [
        { referencia: "POR-DEMO01", descripcion: "Portátil empresarial (demo)", categoria: "Portátiles", costo: "620.00", precio_lista: "800.00", cotizable: true },
        { referencia: "IMP-00009", descripcion: "Impresora sin costo", categoria: "Impresión", costo: null, precio_lista: "90.00", cotizable: false },
      ],
      "POST /cotizaciones": quote({ estado: "BORRADOR", evaluacion: null, total: null, lineas: [] }),
      "POST /cotizaciones/7/calcular": calculated,
      "GET /cotizaciones/7": calculated,
      "GET /cotizaciones/7/eventos": [],
    });
    renderApp(<AppRoutes />, "/cotizaciones/nueva");
    await screen.findByRole("heading", { name: "Nueva cotización" });

    await userEvent.selectOptions(screen.getByLabelText("Canal"), "3");
    await userEvent.type(screen.getByRole("combobox", { name: /buscar referencia/i }), "demo");
    // La referencia no cotizable se muestra marcada.
    expect(await within(await screen.findByRole("listbox")).findByText("No cotizable")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("option", { name: /POR-DEMO01/ }));
    const quantity = screen.getByLabelText("Cantidad de POR-DEMO01");
    await userEvent.clear(quantity);
    await userEvent.type(quantity, "20");

    await userEvent.click(screen.getByRole("button", { name: "Calcular" }));

    expect(await screen.findByText("Lista para emitir")).toBeInTheDocument();
    const created = calls.find((c) => c.method === "POST" && c.path === "/cotizaciones");
    expect(created?.body).toMatchObject({ canal_id: 3, lineas: [{ referencia: "POR-DEMO01", cantidad: 20, descuento_adicional: "0.0000" }] });
    expect(screen.getByRole("button", { name: "Emitir" })).toBeEnabled();
  });

  it("muestra todo el catálogo separado por categoría y permite agregar desde ahí", async () => {
    session("ejecutivo", {
      "GET /catalogo": [
        { referencia: "POR-DEMO01", descripcion: "Portátil empresarial (demo)", categoria: "Portátiles", costo: "620.00", precio_lista: "800.00", cotizable: true },
        { referencia: "POR-00002", descripcion: "Portátil ultraliviano", categoria: "Portátiles", costo: "700.00", precio_lista: "900.00", cotizable: true },
        { referencia: "IMP-00001", descripcion: "Impresora láser", categoria: "Impresión", costo: "70.00", precio_lista: "90.00", cotizable: true },
        { referencia: "IMP-00009", descripcion: "Impresora sin costo", categoria: "Impresión", costo: null, precio_lista: "95.00", cotizable: false },
      ],
    });
    renderApp(<AppRoutes />, "/cotizaciones/nueva");

    // Una pestaña por categoría, con su número de referencias; la primera queda abierta.
    const tabs = await screen.findAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Impresión 2", "Portátiles 2"]);
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText("Impresora láser")).toBeInTheDocument();
    expect(within(panel).getByText("No cotizable")).toBeInTheDocument();
    expect(within(panel).queryByText("Portátil ultraliviano")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /Portátiles/ }));
    expect(within(screen.getByRole("tabpanel")).getByText("Portátil ultraliviano")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Agregar POR-DEMO01" }));
    expect(screen.getByLabelText("Cantidad de POR-DEMO01")).toHaveValue(1);
    // Ya agregada: no se puede repetir.
    expect(screen.queryByRole("button", { name: "Agregar POR-DEMO01" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("tabpanel")).getByText("Ya agregada")).toBeInTheDocument();
  });
});

describe("tablero", () => {
  it("muestra el indicador principal frente a la línea base y las tarjetas", async () => {
    session("gerente", {
      "GET /kpis": {
        alcance: "todos",
        generado_en: "2026-10-05T15:00:00Z",
        totales: { creadas: 14, emitidas: 12, ganadas: 4, perdidas: 2, vencidas: 1, reemplazadas: 1, aprobaciones_resueltas: 3 },
        indicadores: [
          kpi({ codigo: "K2", nombre: "Tiempo de elaboración", valor: 6.8, unidad: "min", linea_base: 24, meta: 7 }),
          kpi(),
          kpi({ codigo: "K11b", nombre: "Aprobaciones dentro del SLA", valor: null, unidad: "%", linea_base: null, meta: 90, sentido: "mayor", muestra: 0 }),
        ],
      },
    });
    renderApp(<AppRoutes />, "/tablero");
    expect(await screen.findByRole("heading", { name: "Indicadores" })).toBeInTheDocument();
    expect(screen.getByText(/Una reducción del 72 %/)).toBeInTheDocument();
    expect(screen.getAllByText(/24 min/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Tiempo de respuesta al canal" })).toBeInTheDocument();
    expect(screen.getByText("Sin datos todavía")).toBeInTheDocument();
    expect(screen.getByText("Emitidas").previousSibling).toHaveTextContent("12");
  });
});
