// Formas de los datos que devuelve la API. Los importes y porcentajes llegan como texto
// decimal ("729.60", "0.0400"); los porcentajes son fracciones (0.04 = 4 %).

export type Role = "ejecutivo" | "aprobador" | "gerente" | "pricing" | "admin";

export type QuoteState =
  | "BORRADOR"
  | "CALCULADA"
  | "PENDIENTE_APROBACION"
  | "EMITIDA"
  | "EN_SEGUIMIENTO"
  | "GANADA"
  | "PERDIDA"
  | "VENCIDA";

export type Evaluation = "LISTA_PARA_EMITIR" | "REQUIERE_APROBACION" | "NO_EMITIBLE";

export interface User {
  id: number;
  usuario: string;
  nombre: string;
  rol: Role;
}

export interface AdminUser extends User {
  email: string;
  activo: boolean;
}

export interface Product {
  referencia: string;
  descripcion: string;
  categoria: string;
  costo: string | null;
  precio_lista: string | null;
  cotizable: boolean;
}

export interface Channel {
  id: number;
  nit: string;
  nombre: string;
  nivel: string;
  ciudad: string;
}

export interface AppliedRule {
  regla: string;
  descripcion: string;
  valor: string | null;
  precio_resultante: string | null;
}

export interface QuoteLine {
  referencia: string;
  cantidad: number;
  descuento_adicional: string;
  descripcion: string | null;
  categoria: string | null;
  estado: "OK" | "NO_COTIZABLE" | "BAJO_COSTO" | null;
  costo: string | null;
  precio_lista: string | null;
  precio_unitario: string | null;
  total: string | null;
  margen: string | null;
  margen_minimo: string | null;
  requiere_aprobacion: boolean;
  bajo_pedido: boolean;
  disponible: number | null;
  cantidad_comprometida: number;
  promocion_fin: string | null;
  reglas_aplicadas: AppliedRule[];
}

export interface PartyRef {
  id: number;
  nombre: string;
  nivel: string | null;
}

export interface QuoteSummary {
  id: number;
  numero: string;
  version: number;
  estado: QuoteState;
  evaluacion: Evaluation | null;
  total: string | null;
  canal: PartyRef;
  ejecutivo: PartyRef;
  recibida_en: string;
  creada_en: string;
  calculada_en: string | null;
  emitida_en: string | null;
  vigente_hasta: string | null;
  cerrada_en: string | null;
  reemplazada: boolean;
  lineas_count: number;
}

export interface ApprovalBrief {
  id: number;
  estado: "PENDIENTE" | "APROBADA" | "RECHAZADA";
  solicitada_en: string;
  vence_en: string;
  escalada: boolean;
  resuelta_en: string | null;
  resuelta_por: string | null;
  comentario: string | null;
}

export interface Quote extends QuoteSummary {
  lineas: QuoteLine[];
  acciones_permitidas: string[];
  puede_crear_version: boolean;
  tiene_pdf: boolean;
  version_anterior_id: number | null;
  /** Solo en una versión reemplazada: la que la sustituyó. */
  version_siguiente_id?: number | null;
  aprobacion: ApprovalBrief | null;
}

export interface QuoteEvent {
  id: number;
  tipo: string;
  ocurrido_en: string;
  usuario: string | null;
  payload: Record<string, unknown>;
}

export interface ApprovalQueueItem {
  id: number;
  solicitada_en: string;
  vence_en: string;
  escalada: boolean;
  escalada_en: string | null;
  sla_restante_segundos: number;
  sla_vencido: boolean;
  solicitante: string | null;
  cotizacion: Quote;
}

export interface FollowUpTask {
  id: number;
  creada_en: string;
  cotizacion: QuoteSummary;
}

export interface AppNotification {
  id: number;
  tipo: string;
  mensaje: string;
  cotizacion_id: number | null;
  leida: boolean;
  creada_en: string;
}

export interface NotificationList {
  no_leidas: number;
  items: AppNotification[];
}

export interface Kpi {
  codigo: string;
  nombre: string;
  valor: number | null;
  unidad: string;
  linea_base: number | null;
  meta: number | null;
  sentido: "menor" | "mayor";
  muestra: number;
  formula: string;
}

export interface Dashboard {
  alcance: "propios" | "todos";
  generado_en: string;
  totales: Record<string, number>;
  indicadores: Kpi[];
}

export interface Level {
  id: number;
  nombre: string;
  descuento: string;
}

export interface VolumeTier {
  id: number;
  cantidad_min: number;
  cantidad_max: number | null;
  descuento: string;
}

export interface Margin {
  id: number;
  categoria: string;
  margen_minimo: string;
}

export interface Promotion {
  id: number;
  referencia: string;
  nombre: string;
  descuento: string;
  fecha_inicio: string;
  fecha_fin: string;
}

export interface Parameter {
  clave: string;
  valor: string;
  descripcion: string;
}
