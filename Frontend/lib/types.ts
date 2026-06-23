export type AttendanceType = 'entrada' | 'salida' | 'colacion_entrada' | 'colacion_salida';

export interface Persona {
  id: string;
  nombre: string;
  rut: string;
  email: string;
  huella_id: number;
  fecha_registro: string;
  sincronizado: boolean;
}

export interface Turno {
  id: string;
  nombre: string;
  inicio: string;
  fin: string;
  dias: string;
  con_colacion: boolean;
  colacion_inicio: string | null;
  colacion_fin: string | null;
}

export interface Asignacion {
  id: string;
  persona_id: string;
  rut: string;
  persona_nombre: string;
  turno_id: string;
  turno_nombre: string;
  fecha_asignacion: string;
  vigente: boolean;
}

export interface Asistencia {
  id: string;
  persona_id: string | null;
  rut: string;
  nombre: string;
  tipo: AttendanceType;
  metodo: string;
  fecha_hora: string;
  origen?: string;
  sincronizado: boolean;
}

export interface DeviceStatus {
  id: string;
  nombre: string;
  ip: string;
  online: boolean;
  marcajes: number;
  mem: number;
  camara: boolean;
  estado?: string;
  tienePassword?: boolean;
  passwordPendiente?: boolean;
  ultimoHeartbeat?: string | null;
  codigoEnrol?: string | null;
}

export interface ErpIntegration {
  id: string;
  nombre: string;
  tipo: 'generic' | 'odoo' | 'defontana' | 'buk' | 'sap';
  webhookUrl: string;
  headers: string;
  fieldMap: string;
  envioAuto: boolean;
  activo: boolean;
  ultimoEnvio?: string | null;
  ultimoEstado?: string;
  createdAt?: string | null;
}

export interface LogEntry {
  id: string;
  type: 'ok' | 'err' | 'info' | 'warn';
  message: string;
  time: string;
}