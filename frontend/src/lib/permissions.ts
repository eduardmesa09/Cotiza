// Qué ve y qué puede hacer cada rol (Tabla 32 del informe). La API valida lo mismo:
// esto solo decide qué mostrar, no reemplaza el control del servidor.

import type { Quote, Role } from "./types";

export interface NavItem {
  to: string;
  label: string;
}

const NAV: Record<Role, NavItem[]> = {
  ejecutivo: [
    { to: "/cotizaciones", label: "Mis cotizaciones" },
    { to: "/seguimiento", label: "Seguimiento" },
    { to: "/tablero", label: "Indicadores" },
  ],
  aprobador: [
    { to: "/aprobaciones", label: "Aprobaciones" },
    { to: "/cotizaciones", label: "Cotizaciones" },
    { to: "/tablero", label: "Indicadores" },
  ],
  gerente: [
    { to: "/tablero", label: "Indicadores" },
    { to: "/aprobaciones", label: "Escalamientos" },
    { to: "/cotizaciones", label: "Cotizaciones" },
  ],
  pricing: [
    { to: "/pricing", label: "Reglas y promociones" },
    { to: "/cotizaciones", label: "Cotizaciones" },
    { to: "/tablero", label: "Indicadores" },
  ],
  admin: [
    { to: "/usuarios", label: "Usuarios" },
    { to: "/parametros", label: "Parámetros" },
  ],
};

export function navFor(role: Role): NavItem[] {
  return NAV[role];
}

export function homeFor(role: Role): string {
  return NAV[role][0].to;
}

export function canAccess(role: Role, path: string): boolean {
  if (path.startsWith("/cotizaciones/nueva")) return role === "ejecutivo";
  return NAV[role].some((item) => path === item.to || path.startsWith(`${item.to}/`));
}

export const ROLE_LABEL: Record<Role, string> = {
  ejecutivo: "Ejecutivo de cuenta",
  aprobador: "Aprobador",
  gerente: "Gerente comercial",
  pricing: "Administrador de pricing",
  admin: "Administrador del sistema",
};

/** Lo que el usuario actual puede hacer con una cotización, combinando su rol, si es suya
 *  y las transiciones que la máquina de estados permite en este momento. */
export function quoteActions(quote: Quote, user: { id: number; rol: Role }, hasUnsavedChanges = false) {
  const owner = user.rol === "ejecutivo" && quote.ejecutivo.id === user.id;
  const allows = (action: string) => owner && quote.acciones_permitidas.includes(action);
  return {
    edit: allows("EDITAR"),
    calculate: allows("CALCULAR"),
    requestApproval: allows("SOLICITAR_APROBACION") && !hasUnsavedChanges,
    // Emitir solo con el cálculo al día: lo que se emite es exactamente lo que se ve.
    issue: allows("EMITIR") && !hasUnsavedChanges,
    win: allows("GANAR"),
    lose: allows("PERDER"),
    newVersion: owner && quote.puede_crear_version,
    downloadPdf: quote.tiene_pdf,
  };
}
