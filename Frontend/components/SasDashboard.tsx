'use client';

import type { ReactNode } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import {
  changePassword,
  createEmpresa,
  deleteEmpresa,
  deleteUsuario,
  updateUsuario,
  deleteDispositivo,
  updateDispositivo,
  verificarDispositivo,
  enviarErp,
  registrarRostro,

  generarPinEnrolamiento,
  generarPasswordDispositivo,
  eliminarPasswordDispositivo,
  registrarHuellaDispositivo,
  reiniciarDispositivo,
  reconectarWifiDispositivo,
  getEmpresas,
  getUsuarios,
  registerUser,
  type Empresa,
  type UsuarioWeb
} from '@/lib/auth-api';
import {
  clearLogs,
  createAsignacion,
  createErp,
  createPersona,
  createTurno,
  deleteAsignacion,
  deleteErp,
  deletePersona,
  deleteTurno,
  getAsignaciones,
  getAsistencias,
  getDispositivos,
  getDuplicadosPendientes,
  getErp,
  getLogs,
  getPersonas,
  getPersonaById,
  getTurnos,
  mergePersonas,
  registrarConsentimiento,
  eliminarDatosBiometricos,
  syncDevices,
  testErp,

} from '@/lib/api';
import type { Asignacion, Asistencia, DeviceStatus, DuplicadoPendiente, ErpIntegration, LogEntry, Persona, Turno } from '@/lib/types';
import { useDeviceWebSocket } from '@/lib/useDeviceWebSocket';

type Section = 'dashboard' | 'asistencias' | 'personas' | 'turnos' | 'asignaciones' | 'dispositivos' | 'erp' | 'logs' | 'usuarios' | 'empresas' | 'duplicados';
type ToastState = { kind: 'success' | 'error'; message: string } | null;
type ErpType = 'generic' | 'odoo' | 'defontana' | 'buk' | 'sap';
type ErpFormState = {
  nombre: string;
  tipo: ErpType;
  webhookUrl: string;
  headers: string;
  fieldMap: string;
  envioAuto: boolean;
};

const deviceBase = process.env.NEXT_PUBLIC_DEVICE_BASE_URL || 'http://192.168.4.1';

const sectionPaths: Record<Section, string> = {
  dashboard: '/',
  asistencias: '/asistencias',
  personas: '/personas',
  turnos: '/turnos',
  asignaciones: '/asignaciones',
  dispositivos: '/dispositivos',
  erp: '/erp',
  logs: '/logs',
  usuarios: '/usuarios',
  empresas: '/empresas',
  duplicados: '/duplicados'
};

const dayCodes = ['L', 'M', 'X', 'J', 'V', 'S', 'D'] as const;
const dayNames: Record<(typeof dayCodes)[number], string> = {
  L: 'Lun',
  M: 'Mar',
  X: 'Mié',
  J: 'Jue',
  V: 'Vie',
  S: 'Sáb',
  D: 'Dom'
};

const erpPresets = {
  generic: {
    headers: '{"Content-Type": "application/json"}',
    fieldMap: '{}',
    hint: 'Cualquier endpoint HTTP POST con JSON.'
  },
  odoo: {
    headers: '{"Content-Type":"application/json","Authorization":"Bearer TOKEN"}',
    fieldMap: '{"persona_id":"employee_id","tipo":"check_type","fecha_hora":"datetime"}',
    hint: 'Odoo usa employee_id y check_type.'
  },
  defontana: {
    headers: '{"Content-Type":"application/json","Authorization":"Bearer API_KEY","X-Company-Id":"EMPRESA_ID"}',
    fieldMap: '{"tipo":"tipoMarcaje","rut":"rutEmpleado"}',
    hint: 'Defontana usa tipoMarcaje: 1 entrada, 2 salida.'
  },
  buk: {
    headers: '{"Content-Type":"application/json","Authorization":"Token token=API_KEY"}',
    fieldMap: '{"tipo":"type","fecha_hora":"datetime"}',
    hint: 'Buk usa type in/out y token por header.'
  },
  sap: {
    headers: '{"Content-Type":"application/json","APIKey":"SAP_KEY"}',
    fieldMap: '{"rut":"PersonnelNumber","fecha_hora":"Date"}',
    hint: 'SAP depende del módulo HCM que uses.'
  }
} as const;

function formatDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return new Intl.DateTimeFormat('es-CL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  }).format(date);
}

function formatTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return new Intl.DateTimeFormat('es-CL', {
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function downloadCsv(rows: string[][], filename: string) {
  const csv = rows
    .map((row) => row.map((cell) => `"${String(cell).split('"').join('""')}"`).join(','))
    .join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function SectionButton({ active, href, children, onClick }: { active: boolean; href: string; children: ReactNode; onClick?: () => void }) {
  return (
    <Link className={`nav-item ${active ? 'active' : ''}`} href={href} onClick={onClick}>
      <span className="nav-item-main">{children}</span>
      <span className="nav-kbd">{active ? 'ON' : ''}</span>
    </Link>
  );
}

function Badge({ tone, children }: { tone: 'success' | 'warning' | 'danger' | 'info'; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function SasDashboard({ initialSection = 'dashboard' }: { initialSection?: Section }) {
  const { user, logout } = useAuth();
  const [section, setSection] = useState<Section>(initialSection);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [asignaciones, setAsignaciones] = useState<Asignacion[]>([]);
  const [asistencias, setAsistencias] = useState<Asistencia[]>([]);
  const [devices, setDevices] = useState<DeviceStatus[]>([]);
  const [erpList, setErpList] = useState<ErpIntegration[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [toast, setToast] = useState<ToastState>(null);
  const [modal, setModal] = useState<'persona' | 'turno' | 'asignacion' | 'erp' | 'usuario' | 'password' | 'empresa' | 'dispositivo' | null>(null);
  const [filterDate, setFilterDate] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterMethod, setFilterMethod] = useState('');
  const [logFilter, setLogFilter] = useState<'all' | 'ok' | 'err' | 'info' | 'warn'>('all');
  const [days, setDays] = useState<string[]>(['L', 'M', 'X', 'J', 'V']);
  const [formError, setFormError] = useState('');

  const [usuarios, setUsuarios] = useState<UsuarioWeb[]>([]);
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [registerForm, setRegisterForm] = useState({ nombre: '', email: '', password: '', rol: 'trabajador', empresa_id: undefined as number | undefined });
  const [editingUsuario, setEditingUsuario] = useState<UsuarioWeb | null>(null);
  const [empresaUserMode, setEmpresaUserMode] = useState<'new' | 'existing'>('new');
  const [empresaForm, setEmpresaForm] = useState<{
    nombre: string; rut_empresa: string; email_contacto: string; telefono: string; direccion: string;
    nombre_usuario: string; email_usuario: string; password_usuario: string;
    usuario_existente_id: number | undefined;
    rol_usuario: string;
  }>({ nombre: '', rut_empresa: '', email_contacto: '', telefono: '', direccion: '', nombre_usuario: '', email_usuario: '', password_usuario: '', usuario_existente_id: undefined, rol_usuario: 'empleador' });
  const [passwordForm, setPasswordForm] = useState({ passwordActual: '', passwordNueva: '', confirmacion: '' });
  const [generatedPin, setGeneratedPin] = useState('');
  const [deviceForm, setDeviceForm] = useState({ nombre: '', ip: '' });
  const [editingDeviceId, setEditingDeviceId] = useState<string | null>(null);
  const [editDeviceName, setEditDeviceName] = useState('');
  const [generatedDevicePassword, setGeneratedDevicePassword] = useState<string | null>(null);
  const [generatingPasswordFor, setGeneratingPasswordFor] = useState<string | null>(null);
  const [rostroPersonaId, setRostroPersonaId] = useState<string | null>(null);
  const [uploadingRostro, setUploadingRostro] = useState(false);
  const [webcamActive, setWebcamActive] = useState(false);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [captureStream, setCaptureStream] = useState<MediaStream | null>(null);
  const liveDevices = useDeviceWebSocket();
  const devicesRef = useRef(devices);
  devicesRef.current = devices;
  const [personaActual, setPersonaActual] = useState<{ id: string; nombre: string; rut: string; email: string; huella_id: number | null; encoding_facial: string | null; fecha_registro: string; activo: boolean } | null>(null);
  const [consentimientoActivo, setConsentimientoActivo] = useState(false);
  const [guardandoConsentimiento, setGuardandoConsentimiento] = useState(false);
  const [eliminandoBiometricos, setEliminandoBiometricos] = useState(false);
  const [huellaModalOpen, setHuellaModalOpen] = useState(false);
  const [huellaPersonaId, setHuellaPersonaId] = useState<string | null>(null);
  const [huellaPersonaNombre, setHuellaPersonaNombre] = useState('');
  const [huellaDeviceId, setHuellaDeviceId] = useState<string | null>(null);
  const [registrandoHuella, setRegistrandoHuella] = useState(false);
  const [huellaMensaje, setHuellaMensaje] = useState('');

  const [personaForm, setPersonaForm] = useState({ nombre: '', rut: '', email: '', consentimiento: false });
  const [turnoForm, setTurnoForm] = useState({ nombre: '', inicio: '08:00', fin: '17:00', con_colacion: false, colacion_inicio: '13:00', colacion_fin: '14:00' });
  const [asignacionForm, setAsignacionForm] = useState({ rut: '', turnoId: '' });
  const [duplicados, setDuplicados] = useState<DuplicadoPendiente[]>([]);
  const [mergingPersonas, setMergingPersonas] = useState(false);
  const [erpForm, setErpForm] = useState<ErpFormState>({
    nombre: 'Nueva integración',
    tipo: 'generic',
    webhookUrl: '',
    headers: erpPresets.generic.headers,
    fieldMap: erpPresets.generic.fieldMap,
    envioAuto: true
  });
  const [erpHint, setErpHint] = useState<string>(erpPresets.generic.hint);

  useEffect(() => {
    setSection(initialSection);
  }, [initialSection]);

  const allowedSections: Section[] = useMemo(() => {
    if (!user) return [];
    if (user.rol === 'admin') return ['dashboard', 'asistencias', 'personas', 'turnos', 'asignaciones', 'dispositivos', 'erp', 'logs', 'usuarios', 'empresas', 'duplicados'];
    if (user.rol === 'empleador') return ['dashboard', 'asistencias', 'personas', 'turnos', 'asignaciones', 'dispositivos', 'erp', 'logs', 'usuarios', 'duplicados'];
    return ['asistencias', 'usuarios'];
  }, [user]);

  useEffect(() => {
    if (!allowedSections.includes(section)) {
      setSection(allowedSections.length > 0 ? allowedSections[0] : 'asistencias');
    }
  }, [section, allowedSections]);

  useEffect(() => {
    let alive = true;

    async function loadData(view: Section) {
      const isTrabajador = user?.rol === 'trabajador';
      const needsPersonas = !isTrabajador && (view === 'dashboard' || view === 'personas' || view === 'asignaciones');
      const needsTurnos = !isTrabajador && (view === 'dashboard' || view === 'turnos' || view === 'asignaciones');
      const needsAsignaciones = !isTrabajador && (view === 'dashboard' || view === 'asignaciones');
      const needsAsistencias = view === 'dashboard' || view === 'asistencias';
      const needsDevices = !isTrabajador && (view === 'dashboard' || view === 'dispositivos');
      const needsErp = !isTrabajador && view === 'erp';
      const needsLogs = !isTrabajador && view === 'logs';
      const needsUsuarios = !isTrabajador && view === 'usuarios';
      const needsEmpresas = !isTrabajador && (view === 'empresas' || (view === 'usuarios' && user?.rol === 'admin'));
      const needsPersonaActual = isTrabajador && view === 'usuarios';
      const needsDuplicados = !isTrabajador && (view === 'dashboard' || view === 'duplicados');

      const [personasRes, turnosRes, asignacionesRes, asistenciasRes, devicesRes, erpRes, logsRes, usuariosRes, empresasRes, personaActualRes, duplicadosRes] = await Promise.all([
        needsPersonas ? getPersonas() : Promise.resolve(null),
        needsTurnos ? getTurnos() : Promise.resolve(null),
        needsAsignaciones ? getAsignaciones() : Promise.resolve(null),
        needsAsistencias ? getAsistencias() : Promise.resolve(null),
        needsDevices ? getDispositivos() : Promise.resolve(null),
        needsErp ? getErp() : Promise.resolve(null),
        needsLogs ? getLogs() : Promise.resolve(null),
        needsUsuarios ? getUsuarios() : Promise.resolve(null),
        needsEmpresas ? getEmpresas() : Promise.resolve(null),
        needsPersonaActual && user?.persona_id ? getPersonaById(user.persona_id) : Promise.resolve(null),
        needsDuplicados ? getDuplicadosPendientes() : Promise.resolve(null)
      ]);

      if (!alive) return;

      if (personasRes) setPersonas(personasRes);
      if (turnosRes) setTurnos(turnosRes);
      if (asignacionesRes) setAsignaciones(asignacionesRes);
      if (asistenciasRes) setAsistencias(asistenciasRes);
      if (devicesRes) {
        const now = Date.now();
        const fiveMinutes = 5 * 60 * 1000;
        setDevices(devicesRes.map((item) => {
          const ultimoHeartbeat = (item as Record<string, unknown>).ultimo_heartbeat as string | null | undefined;
          const online = item.estado === 'activo' && ultimoHeartbeat
            ? (Date.now() - new Date(ultimoHeartbeat).getTime()) < fiveMinutes
            : false;
          return {
            id: item.id,
            nombre: item.nombre,
            ip: item.ip_local || '—',
            online,
            marcajes: 0,
            mem: 0,
            camara: false,
            estado: item.estado,
            tienePassword: (item as Record<string, unknown>).tiene_password as boolean,
            codigoEnrol: (item as Record<string, unknown>).codigo_enrol as string | null | undefined,
            passwordPendiente: (item as Record<string, unknown>).password_pendiente as boolean,
            ultimoHeartbeat
          };
        }));
      }
      if (erpRes) {
        setErpList(erpRes.map((item) => ({
          id: item.id,
          nombre: item.nombre,
          tipo: item.tipo as ErpIntegration['tipo'],
          webhookUrl: item.webhookUrl,
          headers: item.headers,
          fieldMap: item.fieldMap,
          envioAuto: item.envioAuto,
          activo: item.activo,
          ultimoEnvio: item.ultimoEnvio,
          ultimoEstado: item.ultimoEstado
        })));
      }
      if (logsRes) {
        setLogs(logsRes.map((item) => ({
          id: item.id,
          type: item.estado === 'error' ? 'err' : item.estado === 'warn' ? 'warn' : item.estado === 'info' ? 'info' : 'ok',
          message: item.detalle || `Registros ok: ${item.registros_ok}/${item.registros_enviados}`,
          time: item.fecha ? new Intl.DateTimeFormat('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(item.fecha)) : '--:--:--'
        })));
      }
      if (usuariosRes) setUsuarios(usuariosRes);
      if (empresasRes) setEmpresas(empresasRes);
      if (personaActualRes && !('error' in personaActualRes)) {
        setPersonaActual(personaActualRes);
        setConsentimientoActivo(!!(personaActualRes as { encoding_facial: string | null }).encoding_facial);
      }
      if (duplicadosRes) setDuplicados(duplicadosRes);
    }

    loadData(section);
    return () => {
      alive = false;
    };
  }, [section, initialSection]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const sseKeyRef = useRef('');
  useEffect(() => {
    if (liveDevices.length === 0) return;
    const key = liveDevices.map((d) => `${d.id}:${d.online}:${d.estado}:${d.ultimo_heartbeat ?? ''}`).join('|');
    if (key === sseKeyRef.current) return;
    sseKeyRef.current = key;
    setDevices((current) => {
      const map = new Map(current.map((d) => [d.id, d]));
      for (const live of liveDevices) {
        const existing = map.get(live.id);
        if (existing) {
          map.set(live.id, {
            ...existing,
            ip: live.ip || existing.ip,
            online: live.online,
            estado: live.estado,
            ultimoHeartbeat: live.ultimo_heartbeat !== undefined ? live.ultimo_heartbeat : existing.ultimoHeartbeat,
          });
        }
      }
      return Array.from(map.values());
    });
  }, [liveDevices]);

  useEffect(() => {
    const sseUrl = `${process.env.NEXT_PUBLIC_API_URL || `http://${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:5000`}/sse/huellas`;
    let retryTimer: ReturnType<typeof setTimeout>;
    let es: EventSource | null = null;

    function connect() {
      es = new EventSource(sseUrl);
      es.onopen = () => { console.log('[SSE] Conectado a /sse/huellas'); };
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.status === 'ok' && data.persona_id) {
            setRegistrandoHuella(false);
            setHuellaModalOpen(false);
            setToast({ kind: 'success', message: `Huella ID ${data.huella_id} registrada` });
            getPersonas().then((p) => { if (p) setPersonas(p); });
          }
        } catch { /* ignore */ }
      };
      es.onerror = () => {
        es?.close();
        retryTimer = setTimeout(connect, 5000);
      };
    }

    connect();
    return () => {
      clearTimeout(retryTimer);
      if (es) es.close();
    };
  }, []);

  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  useEffect(() => {
    if (user?.rol === 'trabajador') return;
    async function pollDevices() {
      try {
        const res = await getDispositivos();
        if (!res) return;
        const fiveMinutes = 5 * 60 * 1000;
        setDevices((current) => {
          const map = new Map(current.map((d) => [d.id, d]));
          for (const item of res) {
            const ultimoHeartbeat = (item as Record<string, unknown>).ultimo_heartbeat as string | null | undefined;
            const online = item.estado === 'activo' && ultimoHeartbeat
              ? (Date.now() - new Date(ultimoHeartbeat).getTime()) < fiveMinutes
              : false;
            const existing = map.get(item.id);
            if (existing) {
              map.set(item.id, { ...existing, online, estado: item.estado, ultimoHeartbeat });
            } else {
              map.set(item.id, {
                id: item.id,
                nombre: item.nombre,
                ip: item.ip_local || '—',
                online,
                marcajes: 0,
                mem: 0,
                camara: false,
                estado: item.estado,
                tienePassword: (item as Record<string, unknown>).tiene_password as boolean,
                passwordPendiente: (item as Record<string, unknown>).password_pendiente as boolean,
                ultimoHeartbeat,
              });
            }
          }
          return Array.from(map.values());
        });
      } catch { /* ignore */ }
    }
    pollDevices();
    pollRef.current = setInterval(pollDevices, 15000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [user]);

  const stats = useMemo(() => {
    const today = new Date().toDateString();
    const todayCount = asistencias.filter((item) => new Date(item.fecha_hora).toDateString() === today).length;
    const pending = asistencias.filter((item) => !item.sincronizado).length;
    const onlineDevices = devices.filter((item) => item.online).length;
    const facialChecks = asistencias.filter((item) => item.metodo.includes('facial')).length;

    return {
      todayCount,
      pending,
      onlineDevices,
      facialChecks
    };
  }, [asistencias, devices]);

  const filteredAsistencias = useMemo(() => {
    return asistencias.filter((item) => {
      if (filterDate && !item.fecha_hora.startsWith(filterDate)) return false;
      if (filterType && item.tipo !== filterType) return false;
      if (filterMethod && item.metodo !== filterMethod) return false;
      return true;
    });
  }, [asistencias, filterDate, filterMethod, filterType]);

  const visibleLogs = useMemo(() => {
    return logs.filter((item) => logFilter === 'all' || item.type === logFilter);
  }, [logFilter, logs]);

  function pushLog(type: LogEntry['type'], message: string) {
    const time = new Intl.DateTimeFormat('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date());
    setLogs((current) => [...current, { id: crypto.randomUUID(), type, message, time }].slice(-250));
  }

  function showToast(kind: 'success' | 'error', message: string) {
    setToast({ kind, message });
  }

  async function openModal(nextModal: NonNullable<typeof modal>) {
    setFormError('');
    setModal(nextModal);
    if (nextModal === 'empresa') {
      setEmpresaUserMode('new');
      const usuariosData = await getUsuarios();
      if (usuariosData) setUsuarios(usuariosData);
    }
  }

  function closeModal() {
    setModal(null);
    setFormError('');
    setDeviceForm({ nombre: '', ip: '' });
    setEditingUsuario(null);
    setRegisterForm({ nombre: '', email: '', password: '', rol: 'trabajador', empresa_id: undefined });
    setEmpresaForm({ nombre: '', rut_empresa: '', email_contacto: '', telefono: '', direccion: '', nombre_usuario: '', email_usuario: '', password_usuario: '', usuario_existente_id: undefined, rol_usuario: 'empleador' });
  }

  async function refreshData() {
    pushLog('info', 'Actualizando datos del sistema');
    await Promise.all([
      refreshSection(section),
      section === 'dashboard' ? Promise.all([refreshSection('personas'), refreshSection('turnos')]) : Promise.resolve()
    ]);
    showToast('success', 'Datos actualizados');
    pushLog('ok', 'Datos actualizados correctamente');
  }

  async function refreshSection(view: Section) {
    if (view === 'dashboard' || view === 'asistencias') {
      const asistenciasRes = await getAsistencias();
      if (asistenciasRes) setAsistencias(asistenciasRes);
    }

    if (view === 'dashboard' || view === 'personas' || view === 'asignaciones') {
      const personasRes = await getPersonas();
      if (personasRes) setPersonas(personasRes);
    }

    if (view === 'dashboard' || view === 'turnos' || view === 'asignaciones') {
      const turnosRes = await getTurnos();
      if (turnosRes) setTurnos(turnosRes);
    }

    if (view === 'dashboard' || view === 'asignaciones') {
      const asignacionesRes = await getAsignaciones();
      if (asignacionesRes) setAsignaciones(asignacionesRes);
    }

    if (view === 'dashboard' || view === 'dispositivos') {
      const devicesRes = await getDispositivos();
      if (devicesRes) {
        const fiveMinutes = 5 * 60 * 1000;
        setDevices(devicesRes.map((item) => {
          const ultimoHeartbeat = (item as Record<string, unknown>).ultimo_heartbeat as string | null | undefined;
          const online = item.estado === 'activo' && ultimoHeartbeat
            ? (Date.now() - new Date(ultimoHeartbeat).getTime()) < fiveMinutes
            : false;
          return {
            id: item.id,
            nombre: item.nombre,
            ip: item.ip_local || '—',
            online,
            marcajes: 0,
            mem: 0,
            camara: false,
            estado: item.estado,
            codigoEnrol: (item as Record<string, unknown>).codigo_enrol as string | null | undefined,
            ultimoHeartbeat
          };
        }));
      }
    }

    if (view === 'dashboard' || view === 'duplicados') {
      const duplicadosRes = await getDuplicadosPendientes();
      if (duplicadosRes) setDuplicados(duplicadosRes);
    }

    if (view === 'erp') {
      const erpRes = await getErp();
      if (erpRes) {
        setErpList(erpRes.map((item) => ({
          id: item.id,
          nombre: item.nombre,
          tipo: item.tipo as ErpIntegration['tipo'],
          webhookUrl: item.webhookUrl,
          headers: item.headers,
          fieldMap: item.fieldMap,
          envioAuto: item.envioAuto,
          activo: item.activo,
          ultimoEnvio: item.ultimoEnvio,
          ultimoEstado: item.ultimoEstado
        })));
      }
    }

    if (view === 'logs') {
      const logsRes = await getLogs();
      if (logsRes) {
        setLogs(logsRes.map((item) => ({
          id: item.id,
          type: item.estado === 'error' ? 'err' : item.estado === 'warn' ? 'warn' : item.estado === 'info' ? 'info' : 'ok',
          message: item.detalle || `Registros ok: ${item.registros_ok}/${item.registros_enviados}`,
          time: item.fecha ? new Intl.DateTimeFormat('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(item.fecha)) : '--:--:--'
        })));
      }
    }
  }

  async function handleCreatePersona() {
    const nombre = personaForm.nombre.trim();
    const rut = personaForm.rut.trim();

    if (!nombre || !rut) {
      setFormError('Nombre y RUT son obligatorios');
      return;
    }

    if (!personaForm.consentimiento) {
      setFormError('Debe aceptar la política de privacidad antes de registrar datos biométricos');
      return;
    }

    const result = await createPersona({ nombre, rut, email: personaForm.email.trim(), consentimiento: personaForm.consentimiento });

    if (result && 'ok' in result && result.ok) {
      pushLog('ok', `Persona creada: ${nombre}`);
      showToast('success', `Persona ${nombre} guardada. Complete el registro de huella y rostro desde el dispositivo físico (ESP32).`);
      closeModal();
      setPersonaForm({ nombre: '', rut: '', email: '', consentimiento: false });
      await refreshData();
      return;
    }

    showToast('error', 'No se pudo guardar la persona en la base de datos');
  }

  async function handleCreateTurno() {
    const nombre = turnoForm.nombre.trim();
    if (!nombre) {
      setFormError('El nombre del turno es obligatorio');
      return;
    }

    const dias = days.join('');
    const result = await createTurno({
      nombre, inicio: turnoForm.inicio, fin: turnoForm.fin, dias,
      con_colacion: turnoForm.con_colacion,
      colacion_inicio: turnoForm.con_colacion ? turnoForm.colacion_inicio : null,
      colacion_fin: turnoForm.con_colacion ? turnoForm.colacion_fin : null
    });

    if (result && 'ok' in result && result.ok) {
      pushLog('ok', `Turno creado: ${nombre}`);
      showToast('success', `Turno ${nombre} creado`);
      closeModal();
      setTurnoForm({ nombre: '', inicio: '08:00', fin: '17:00', con_colacion: false, colacion_inicio: '13:00', colacion_fin: '14:00' });
      setDays(['L', 'M', 'X', 'J', 'V']);
      await refreshData();
      return;
    }

    showToast('error', 'No se pudo guardar el turno en la base de datos');
  }

  async function handleCreateAsignacion() {
    if (!asignacionForm.rut || !asignacionForm.turnoId) {
      setFormError('Selecciona una persona y un turno');
      return;
    }

    const result = await createAsignacion({ rut: asignacionForm.rut, turno_id: asignacionForm.turnoId });

    if (result && 'ok' in result && result.ok) {
      pushLog('ok', `Asignación creada para RUT ${asignacionForm.rut}`);
      showToast('success', 'Asignación creada');
      closeModal();
      setAsignacionForm({ rut: '', turnoId: '' });
      await refreshData();
      return;
    }

    showToast('error', 'No se pudo guardar la asignación en la base de datos');
  }

  function handleErpTypeChange(value: keyof typeof erpPresets) {
    const preset = erpPresets[value];
    setErpForm((current) => ({
      ...current,
      tipo: value,
      headers: preset.headers,
      fieldMap: preset.fieldMap
    }));
    setErpHint(preset.hint);
  }

  async function handleSaveErp() {
    const nombre = erpForm.nombre.trim();
    const webhookUrl = erpForm.webhookUrl.trim();

    if (!nombre || !webhookUrl) {
      setFormError('Nombre y URL son obligatorios');
      return;
    }

    const result = await createErp({
      nombre,
      tipo: erpForm.tipo,
      webhookUrl,
      headers: erpForm.headers,
      fieldMap: erpForm.fieldMap,
      envioAuto: erpForm.envioAuto,
      activo: true
    });

    if (result && 'ok' in result && result.ok) {
      const erpRes = await getErp();
      setErpList((erpRes ?? []).map((item) => ({
        id: item.id,
        nombre: item.nombre,
        tipo: item.tipo as ErpIntegration['tipo'],
        webhookUrl: item.webhookUrl,
        headers: item.headers,
        fieldMap: item.fieldMap,
        envioAuto: item.envioAuto,
        activo: item.activo
      })));
      pushLog('ok', `ERP agregado: ${nombre}`);
      showToast('success', `Integración ${nombre} guardada`);
      closeModal();
      setErpForm({ nombre: 'Nueva integración', tipo: 'generic', webhookUrl: '', headers: erpPresets.generic.headers, fieldMap: erpPresets.generic.fieldMap, envioAuto: true });
      setErpHint(erpPresets.generic.hint);
      return;
    }

    showToast('error', 'No se pudo guardar la integración ERP');
  }

  async function handleDeletePersona(personaId: string) {
    const result = await deletePersona(personaId);
    if (result && 'ok' in result && result.ok) {
      setPersonas((current) => current.filter((item) => item.id !== personaId));
      const label = user?.rol === 'admin' ? 'eliminada' : 'desactivada';
      pushLog('ok', `Persona ${label}: ${personaId}`);
      showToast('success', `Persona ${label}`);
      return;
    }

    showToast('error', 'No se pudo desactivar la persona');
  }

  function openHuellaModal(personaId: string, personaNombre: string) {
    setHuellaPersonaId(personaId);
    setHuellaPersonaNombre(personaNombre);
    setHuellaDeviceId(null);
    setHuellaMensaje('');
    setRegistrandoHuella(false);
    setHuellaModalOpen(true);
  }

  function closeHuellaModal() {
    setHuellaModalOpen(false);
    setHuellaPersonaId(null);
    setRegistrandoHuella(false);
  }

  async function handleRegistrarHuella() {
    if (!huellaDeviceId || !huellaPersonaId) return;
    setRegistrandoHuella(true);
    setHuellaMensaje('Enviando solicitud al dispositivo...');
    try {
      await registrarHuellaDispositivo(huellaDeviceId, huellaPersonaId);
      setHuellaMensaje('Solicitud enviada. Coloque el dedo en el dispositivo. El LED verde indica que está listo.');
    } catch {
      setRegistrandoHuella(false);
      setHuellaMensaje('Error al enviar la solicitud');
      showToast('error', 'Error al enviar solicitud de huella');
    }
  }

  async function handleDeleteTurno(turnoId: string) {
    const result = await deleteTurno(turnoId);
    if (result && 'ok' in result && result.ok) {
      setTurnos((current) => current.filter((item) => item.id !== turnoId));
      pushLog('ok', `Turno eliminado: ${turnoId}`);
      showToast('success', 'Turno eliminado');
      return;
    }

    showToast('error', 'No se pudo eliminar el turno');
  }

  async function handleDeleteAsignacion(asignacionId: string) {
    const result = await deleteAsignacion(asignacionId);
    if (result && 'ok' in result && result.ok) {
      setAsignaciones((current) => current.filter((item) => item.id !== asignacionId));
      pushLog('ok', `Asignación eliminada: ${asignacionId}`);
      showToast('success', 'Asignación eliminada');
      return;
    }

    showToast('error', 'No se pudo eliminar la asignación');
  }

  async function handleDeleteDispositivo(dispositivoId: string, deviceName: string) {
    if (!window.confirm(`¿Eliminar el dispositivo "${deviceName}"? Esta acción no se puede deshacer.`)) return;
    const result = await deleteDispositivo(dispositivoId);
    if (result && 'ok' in result && result.ok) {
      setDevices((current) => current.filter((item) => item.id !== dispositivoId));
      pushLog('ok', `Dispositivo eliminado: ${deviceName}`);
      showToast('success', 'Dispositivo eliminado');
      return;
    }
    showToast('error', 'No se pudo eliminar el dispositivo');
  }

  async function handleDeleteErp(erpId: string) {
    const result = await deleteErp(erpId);
    if (result && 'ok' in result && result.ok) {
      const erpRes = await getErp();
      setErpList((erpRes ?? []).map((item) => ({
        id: item.id,
        nombre: item.nombre,
        tipo: item.tipo as ErpIntegration['tipo'],
        webhookUrl: item.webhookUrl,
        headers: item.headers,
        fieldMap: item.fieldMap,
        envioAuto: item.envioAuto,
        activo: item.activo
      })));
      pushLog('ok', `ERP eliminado: ${erpId}`);
      showToast('success', 'Integración eliminada');
      return;
    }

    showToast('error', 'No se pudo eliminar la integración');
  }

  async function handleTestErp(erpId: string, nombre: string) {
    const result = await testErp(erpId);
    if (result && 'ok' in result && result.ok) {
      pushLog('ok', `ERP verificado: ${nombre}`);
      showToast('success', `Verificación ejecutada para ${nombre}`);
      return;
    }

    showToast('error', `No se pudo probar ${nombre}`);
  }

  async function handleEnviarErp(erpId: string, nombre: string) {
    const result = await enviarErp(erpId);
    if (result && 'ok' in result && result.ok) {
      pushLog('ok', `ERP enviado a ${nombre}: ${result.enviados} registros`);
      showToast('success', `Enviados ${result.enviados} registros a ${nombre}`);
      await refreshData();
      return;
    }
    showToast('error', `No se pudo enviar a ${nombre}`);
  }

  async function handleClearLogs() {
    const result = await clearLogs();
    if (result && 'ok' in result && result.ok) {
      setLogs([]);
      showToast('success', 'Logs limpiados');
      return;
    }

    showToast('error', 'No se pudieron limpiar los logs');
  }

  function handleExportCsv() {
    downloadCsv(
      [['Nombre', 'Tipo', 'Metodo', 'Fecha', 'Sincronizado'], ...asistencias.map((item) => [item.nombre, item.tipo, item.metodo, item.fecha_hora, item.sincronizado ? 'si' : 'no'])],
      'asistencias.csv'
    );
    pushLog('info', 'CSV exportado');
    showToast('success', 'CSV exportado');
  }

  async function handleSyncAll() {
    pushLog('info', 'Enviando comando de sincronizacion a dispositivos...');
    const res = await syncDevices();
    if (res && 'ok' in res && res.ok) {
      pushLog('ok', `Sync remoto: ${res.mensaje}`);
      showToast('success', res.mensaje);
    } else {
      pushLog('err', 'Error enviando sync a dispositivos');
      showToast('error', (res as { error?: string })?.error || 'No se pudo enviar sync');
    }
    await refreshData();
  }

  async function handleDeviceSync(ip: string) {
    pushLog('info', `Sincronización solicitada para dispositivo`);
    const res = await syncDevices();
    if (res && 'ok' in res && res.ok) {
      pushLog('ok', res.mensaje);
      showToast('success', res.mensaje);
    } else {
      pushLog('err', 'Error enviando comando de sincronización');
      showToast('error', (res as { error?: string })?.error || 'Error');
    }
  }

  async function handleReiniciarDispositivo(id: string, nombre: string) {
    if (!confirm(`¿Desea reiniciar el dispositivo "${nombre}"? El dispositivo se reiniciará y tardará unos segundos en volver a estar en línea.`)) return;
    showToast('success', `Enviando comando de reinicio a ${nombre}...`);
    try {
      const res = await reiniciarDispositivo(id);
      if (res && res.ok) {
        pushLog('ok', `Reinicio enviado: ${nombre}`);
        showToast('success', res.mensaje || `Reinicio enviado a ${nombre}`);
      } else {
        showToast('error', (res as { error?: string })?.error || 'No se pudo enviar el comando de reinicio');
      }
    } catch {
      showToast('error', 'Error de conexión al enviar comando de reinicio');
    }
  }

  async function handleReconectarWifiDispositivo(id: string, nombre: string) {
    if (!confirm(`¿Desea reconectar el WiFi del dispositivo "${nombre}"?`)) return;
    showToast('success', `Enviando comando de reconexión WiFi a ${nombre}...`);
    try {
      const res = await reconectarWifiDispositivo(id);
      if (res && res.ok) {
        pushLog('ok', `Reconexión WiFi enviada: ${nombre}`);
        showToast('success', res.mensaje || `Reconexión WiFi enviada a ${nombre}`);
      } else {
        showToast('error', (res as { error?: string })?.error || 'No se pudo enviar el comando de reconexión WiFi');
      }
    } catch {
      showToast('error', 'Error de conexión al enviar comando de reconexión WiFi');
    }
  }

  async function handleToggleConsentimiento() {
    if (!personaActual) return;
    setGuardandoConsentimiento(true);
    const res = await registrarConsentimiento(Number(personaActual.id), '1.0', 'web');
    setGuardandoConsentimiento(false);
    if (!res) {
      showToast('error', 'Error de conexión al actualizar consentimiento');
      return;
    }
    if ('ok' in res && res.ok) {
      setConsentimientoActivo(!consentimientoActivo);
      showToast('success', consentimientoActivo ? 'Consentimiento revocado' : 'Consentimiento registrado');
    } else {
      showToast('error', (res as { error: string }).error || 'Error al actualizar consentimiento');
    }
  }

  async function handleEliminarBiometricos() {
    if (!personaActual) return;
    setEliminandoBiometricos(true);
    const res = await eliminarDatosBiometricos(Number(personaActual.id));
    setEliminandoBiometricos(false);
    if (!res) {
      showToast('error', 'Error de conexión al eliminar datos biométricos');
      return;
    }
    if ('ok' in res && res.ok) {
      setPersonaActual((prev) => prev ? { ...prev, encoding_facial: null } : null);
      setConsentimientoActivo(false);
      showToast('success', 'Datos biométricos eliminados correctamente');
      pushLog('info', 'Datos biométricos eliminados por el usuario');
    } else {
      showToast('error', (res as { error: string }).error || 'Error al eliminar datos biométricos');
    }
  }

  async function handleRostroUpload(personaId: string) {
    const persona = personas.find((p) => p.id === personaId);
    const rut = persona?.rut || personaId;
    setRostroPersonaId(rut);
    setCapturedImage(null);
    setWebcamActive(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' } });
      setCaptureStream(stream);
    } catch {
      showToast('error', 'No se pudo acceder a la cámara. Verifica los permisos.');
      setWebcamActive(false);
    }
  }

  function handleWebcamCapture() {
    const video = document.getElementById('webcam-video') as HTMLVideoElement | null;
    if (!video) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);
    setCapturedImage(canvas.toDataURL('image/jpeg', 0.85));
  }

  function handleWebcamRetake() {
    setCapturedImage(null);
  }

  function handleWebcamCancel() {
    if (captureStream) {
      captureStream.getTracks().forEach((track) => track.stop());
    }
    setWebcamActive(false);
    setCapturedImage(null);
    setCaptureStream(null);
    setRostroPersonaId(null);
  }

  async function handleWebcamConfirm() {
    if (!capturedImage || !rostroPersonaId) return;
    setUploadingRostro(true);
    try {
      const base64 = capturedImage.split(',')[1];
      const result = await registrarRostro(rostroPersonaId, base64);
      if (result && 'ok' in result && result.ok) {
        pushLog('ok', `Rostro registrado para ID ${rostroPersonaId}`);
        showToast('success', 'Rostro registrado correctamente');
        if (personaActual && personaActual.id === rostroPersonaId) {
          setPersonaActual((prev) => prev ? { ...prev, encoding_facial: 'registered' } : prev);
        }
      } else {
        const msg = result && 'error' in result ? String(result.error) : 'No se pudo registrar el rostro';
        showToast('error', msg);
      }
    } catch (e) {
      showToast('error', e instanceof Error ? e.message : 'Error al registrar rostro');
    }
    setUploadingRostro(false);
    handleWebcamCancel();
  }

  async function handleGenerarPin() {
    setFormError('');
    const nombre = deviceForm.nombre.trim() || 'Nuevo dispositivo';
    const result = await generarPinEnrolamiento(nombre);
    if (result && 'ok' in result && result.ok) {
      setGeneratedPin(result.pin);
      showToast('success', `PIN generado para "${nombre}"`);
    } else {
      const msg = result && 'error' in result ? String(result.error) : 'Error al generar PIN';
      setFormError(msg);
    }
  }

  async function handleGenerarPassword(dispositivoId: string, nombre: string, yaTiene: boolean) {
    if (yaTiene && !window.confirm(`"${nombre}" ya tiene una contraseña. Se sobrescribirá. ¿Continuar?`)) return;
    setGeneratingPasswordFor(dispositivoId);
    const result = await generarPasswordDispositivo(dispositivoId);
    setGeneratingPasswordFor(null);
    if (result && 'ok' in result && result.ok) {
      setGeneratedDevicePassword(result.password);
      setDevices((current) =>
        current.map((d) => (d.id === dispositivoId ? { ...d, tienePassword: true, passwordPendiente: true } : d))
      );
      showToast('success', `Contraseña generada para "${nombre}"`);
    } else {
      const msg = result && 'error' in result ? String(result.error) : 'Error al generar contraseña';
      showToast('error', msg);
    }
  }

  async function handleEliminarPassword(dispositivoId: string, nombre: string) {
    if (!window.confirm(`¿Eliminar la contraseña de "${nombre}"? El dispositivo quedará sin protección.`)) return;
    const result = await eliminarPasswordDispositivo(dispositivoId);
    if (result && 'ok' in result && result.ok) {
      setDevices((current) =>
        current.map((d) => (d.id === dispositivoId ? { ...d, tienePassword: false, passwordPendiente: false } : d))
      );
      showToast('success', `Contraseña eliminada para "${nombre}"`);
    } else {
      const msg = result && 'error' in result ? String(result.error) : 'Error al eliminar contraseña';
      showToast('error', msg);
    }
  }

  async function handleVerificarDispositivo() {
    const ip = deviceForm.ip.trim();
    if (!ip) {
      showToast('error', 'Ingresa una IP para verificar');
      return;
    }
    const result = await verificarDispositivo(ip);
    if (result && 'ok' in result && result.ok) {
      showToast('success', 'Dispositivo verificado');
    } else {
      const mensaje = result && 'error' in result ? String(result.error) : 'No responde';
      showToast('error', mensaje);
    }
  }

  async function handleUpdateDeviceName(dispositivoId: string) {
    const nombre = editDeviceName.trim();
    if (!nombre) {
      showToast('error', 'El nombre no puede estar vacío');
      return;
    }
    const result = await updateDispositivo(dispositivoId, nombre);
    if (result && 'ok' in result && result.ok) {
      setDevices((current) => current.map((d) => (d.id === dispositivoId ? { ...d, nombre } : d)));
      pushLog('ok', `Dispositivo renombrado: ${nombre}`);
      showToast('success', 'Nombre actualizado');
      setEditingDeviceId(null);
      return;
    }
    showToast('error', 'No se pudo actualizar el nombre');
  }

  async function handleCreateEmpresa() {
    const { nombre } = empresaForm;
    if (!nombre.trim()) {
      setFormError('El nombre de la empresa es obligatorio');
      return;
    }

    const base = {
      nombre: nombre.trim(),
      rut_empresa: empresaForm.rut_empresa.trim(),
      email_contacto: empresaForm.email_contacto.trim(),
      telefono: empresaForm.telefono.trim(),
      direccion: empresaForm.direccion.trim(),
      rol_usuario: empresaForm.rol_usuario,
    };

    try {
      if (empresaUserMode === 'new') {
        const { nombre_usuario, email_usuario, password_usuario } = empresaForm;
        if (!nombre_usuario.trim() || !email_usuario.trim() || !password_usuario.trim()) {
          setFormError('Completa todos los campos del usuario (nombre, email y contraseña)');
          return;
        }
        if (password_usuario.length < 4) {
          setFormError('La contraseña debe tener al menos 4 caracteres');
          return;
        }
        const result = await createEmpresa({
          ...base,
          mode: 'new',
          nombre_usuario: nombre_usuario.trim(),
          email_usuario: email_usuario.trim().toLowerCase(),
          password_usuario: password_usuario
        });

        if (result && 'ok' in result && result.ok) {
          showToast('success', 'Empresa creada con usuario asignado');
          setEmpresaForm({ nombre: '', rut_empresa: '', email_contacto: '', telefono: '', direccion: '', nombre_usuario: '', email_usuario: '', password_usuario: '', usuario_existente_id: undefined, rol_usuario: 'empleador' });
          closeModal();
          await refreshData();
        }
      } else {
        if (!empresaForm.usuario_existente_id) {
          setFormError('Selecciona un usuario existente');
          return;
        }
        const result = await createEmpresa({
          ...base,
          mode: 'existing',
          usuario_id: empresaForm.usuario_existente_id
        });

        if (result && 'ok' in result && result.ok) {
          showToast('success', 'Empresa creada con usuario asignado');
          setEmpresaForm({ nombre: '', rut_empresa: '', email_contacto: '', telefono: '', direccion: '', nombre_usuario: '', email_usuario: '', password_usuario: '', usuario_existente_id: undefined, rol_usuario: 'empleador' });
          closeModal();
          await refreshData();
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al crear empresa';
      showToast('error', msg);
      pushLog('err', msg);
    }
  }

  async function handleDeleteEmpresa(empresaId: number, nombre: string) {
    if (!window.confirm(`¿Eliminar la empresa "${nombre}"? Se borrarán todos sus datos.`)) return;

    const result = await deleteEmpresa(empresaId);

    if (result && 'ok' in result && result.ok) {
      showToast('success', 'Empresa eliminada');
      await refreshData();
      return;
    }

    showToast('error', result && 'error' in result ? String(result.error) : 'Error al eliminar empresa');
  }

  async function handleRegisterUser() {
    const { nombre, email, password, rol, empresa_id } = registerForm;

    if (!nombre.trim() || !email.trim() || !password) {
      setFormError('Completa todos los campos obligatorios');
      return;
    }

    if (password.length < 4) {
      setFormError('La contraseña debe tener al menos 4 caracteres');
      return;
    }

    if (user?.rol === 'admin' && !empresa_id) {
      setFormError('Selecciona una empresa');
      return;
    }

    const result = await registerUser({
      nombre: nombre.trim(),
      email: email.trim().toLowerCase(),
      password,
      rol,
      empresa_id: user?.rol === 'admin' ? empresa_id : undefined
    });

    if (result && 'ok' in result && result.ok) {
      showToast('success', 'Usuario creado correctamente');
      setRegisterForm({ nombre: '', email: '', password: '', rol: 'trabajador', empresa_id: undefined });
      closeModal();
      await refreshData();
      return;
    }

    const msg = result && 'error' in result ? String(result.error) : 'Error al crear usuario';
    showToast('error', msg);
  }

  async function handleDeleteUsuario(userId: number, empresaId: number, userName: string) {
    if (!window.confirm(`¿Eliminar a ${userName}? Esta acción no se puede deshacer.`)) return;

    const result = await deleteUsuario(userId, empresaId);

    if (result && 'ok' in result && result.ok) {
      showToast('success', 'Usuario eliminado');
      await refreshData();
      return;
    }

    const msg = result && 'error' in result ? String(result.error) : 'Error al eliminar usuario';
    showToast('error', msg);
  }

  function handleEditUsuario(usuario: UsuarioWeb) {
    setEditingUsuario(usuario);
    setRegisterForm({
      nombre: usuario.nombre,
      email: usuario.email,
      password: '',
      rol: usuario.rol,
      empresa_id: usuario.empresa_id
    });
    setFormError('');
    setModal('usuario');
  }

  async function handleUpdateUsuario() {
    if (!editingUsuario) return;
    const { nombre, email, password, rol, empresa_id } = registerForm;

    if (!nombre.trim() || !email.trim()) {
      setFormError('Nombre y email son obligatorios');
      return;
    }

    if (password && password.length < 4) {
      setFormError('La contraseña debe tener al menos 4 caracteres');
      return;
    }

    const payload: { nombre?: string; email?: string; password?: string; rol?: string; empresa_id?: number; activo?: boolean } = {
      nombre: nombre.trim(),
      email: email.trim().toLowerCase()
    };

    if (password) payload.password = password;
    if (user?.rol === 'admin' && empresa_id) payload.empresa_id = empresa_id;
    if ((user?.rol === 'admin' || user?.rol === 'empleador') && rol) payload.rol = rol;

    const result = await updateUsuario(editingUsuario.id, payload);

    if (result && 'ok' in result && result.ok) {
      showToast('success', 'Usuario actualizado correctamente');
      setEditingUsuario(null);
      setRegisterForm({ nombre: '', email: '', password: '', rol: 'trabajador', empresa_id: undefined });
      closeModal();
      await refreshData();
      return;
    }

    const msg = result && 'error' in result ? String(result.error) : 'Error al actualizar usuario';
    showToast('error', msg);
  }

  async function handleChangePassword() {
    const { passwordActual, passwordNueva, confirmacion } = passwordForm;

    if (!passwordActual || !passwordNueva || !confirmacion) {
      setFormError('Completa todos los campos');
      return;
    }

    if (passwordNueva.length < 4) {
      setFormError('La nueva contraseña debe tener al menos 4 caracteres');
      return;
    }

    if (passwordNueva !== confirmacion) {
      setFormError('Las contraseñas no coinciden');
      return;
    }

    const result = await changePassword(passwordActual, passwordNueva);

    if (result && 'ok' in result && result.ok) {
      showToast('success', 'Contraseña actualizada correctamente');
      setPasswordForm({ passwordActual: '', passwordNueva: '', confirmacion: '' });
      closeModal();
      return;
    }

    const msg = result && 'error' in result ? String(result.error) : 'Error al cambiar contraseña';
    setFormError(msg);
  }

  const recentAsistencias = asistencias.slice(0, 6);
  const dashboardDevices = devices;
  const currentTitle = {
    dashboard: 'Panel principal',
    asistencias: 'Asistencias',
    personas: 'Personas',
    turnos: 'Turnos',
    asignaciones: 'Asignaciones',
    dispositivos: 'Dispositivos',
    duplicados: 'Duplicados',
    erp: 'Integraciones',
    logs: 'Registro de actividad',
    usuarios: 'Usuarios',
    empresas: 'Empresas'
  }[section];

  const currentSubtitle = {
    dashboard: 'Métricas, estado del sistema y acceso rápido a las funciones principales.',
    asistencias: 'Consulta y filtra los registros de asistencia del personal.',
    personas: 'Administra las personas registradas y sus datos biométricos.',
    turnos: 'Define los horarios y jornadas de trabajo.',
    asignaciones: 'Asigna turnos a las personas de la organización.',
    dispositivos: 'Supervisa y administra los dispositivos de registro.',
    duplicados: 'Revisa y resuelve conflictos de personas duplicadas en el sistema.',
    erp: 'Conecta el sistema con tus plataformas externas.',
    logs: 'Revisa el historial de eventos y operaciones del sistema.',
    usuarios: 'Administra las cuentas de acceso y sus permisos.',
    empresas: 'Cada empresa opera con sus propios datos y configuraciones.'
  }[section];

  return (
    <div className="app-shell">
      <div className={`sidebar-backdrop ${sidebarOpen ? 'open' : ''}`} onClick={() => setSidebarOpen(false)} role="presentation" />
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-mobile-top">
          <button className="btn btn-secondary mobile-close-btn" type="button" onClick={() => setSidebarOpen(false)}>
            Cerrar menú
          </button>
        </div>
        <div className="brand">
          <div className="brand-mark">SAS</div>
          <div className="brand-copy">
            <div className="brand-title">Sistema de Asistencia</div>
            <div className="brand-subtitle">Control de Asistencia</div>
          </div>
        </div>

        <div className="nav-group">
          <div className="nav-label">Panel</div>
          <SectionButton active={section === 'dashboard'} href={sectionPaths.dashboard} onClick={() => setSidebarOpen(false)}>
            <span>Dashboard</span>
          </SectionButton>
          <SectionButton active={section === 'asistencias'} href={sectionPaths.asistencias} onClick={() => setSidebarOpen(false)}>
            <span>Asistencias</span>
          </SectionButton>
        </div>

        {(user?.rol === 'admin' || user?.rol === 'empleador') && (
          <div className="nav-group">
            <div className="nav-label">Gestión</div>
            <SectionButton active={section === 'personas'} href={sectionPaths.personas} onClick={() => setSidebarOpen(false)}>
              <span>Personas</span>
            </SectionButton>
            <SectionButton active={section === 'turnos'} href={sectionPaths.turnos} onClick={() => setSidebarOpen(false)}>
              <span>Turnos</span>
            </SectionButton>
            <SectionButton active={section === 'asignaciones'} href={sectionPaths.asignaciones} onClick={() => setSidebarOpen(false)}>
              <span>Asignaciones</span>
            </SectionButton>
          </div>
        )}

        {(user?.rol === 'admin' || user?.rol === 'empleador') && (
          <div className="nav-group">
            <div className="nav-label">Sistema</div>
            {user?.rol === 'admin' && (
              <SectionButton active={section === 'empresas'} href={sectionPaths.empresas} onClick={() => setSidebarOpen(false)}>
                <span>Empresas</span>
              </SectionButton>
            )}
            <SectionButton active={section === 'dispositivos'} href={sectionPaths.dispositivos} onClick={() => setSidebarOpen(false)}>
              <span>Dispositivos</span>
            </SectionButton>
            <SectionButton active={section === 'duplicados'} href={sectionPaths.duplicados} onClick={() => setSidebarOpen(false)}>
              <span>Duplicados {duplicados.length > 0 ? <span className="badge danger" style={{ marginLeft: 6, fontSize: '0.7rem', padding: '1px 6px' }}>{duplicados.length}</span> : null}</span>
            </SectionButton>
            <SectionButton active={section === 'erp'} href={sectionPaths.erp} onClick={() => setSidebarOpen(false)}>
              <span>ERP</span>
            </SectionButton>
            <SectionButton active={section === 'logs'} href={sectionPaths.logs} onClick={() => setSidebarOpen(false)}>
              <span>Logs</span>
            </SectionButton>
            <SectionButton active={section === 'usuarios'} href={sectionPaths.usuarios} onClick={() => setSidebarOpen(false)}>
              <span>Usuarios</span>
            </SectionButton>
          </div>
        )}

        {user?.rol === 'trabajador' && (
          <div className="nav-group">
            <div className="nav-label">Mi cuenta</div>
            <SectionButton active={section === 'usuarios'} href={sectionPaths.usuarios} onClick={() => setSidebarOpen(false)}>
              <span>Mi cuenta</span>
            </SectionButton>
          </div>
        )}

        {user && (
          <div className="sidebar-card">
            <div className="sidebar-card-title">{user.empresa_nombre}</div>
            <div className="sidebar-card-subtitle" style={{ marginTop: 4 }}>
              {user.nombre} · {user.rol === 'admin' ? 'Administrador' : user.rol === 'empleador' ? 'Administrador de empresa' : 'Trabajador'}
            </div>
          </div>
        )}
      </aside>

      <main className="content">
        <header className="topbar">
          <div className="title-block">
            <button className="btn btn-secondary mobile-menu-btn" type="button" onClick={() => setSidebarOpen(true)}>
              Menú
            </button>
            <span className="eyebrow">SAS</span>
            <h1 className="page-title">{currentTitle}</h1>
            <p className="page-subtitle">{currentSubtitle}</p>
          </div>

          <div className="top-actions">
            {(user?.rol === 'admin' || user?.rol === 'empleador') && (
              <span className="chip"><strong>{stats.onlineDevices}</strong> dispositivos en línea</span>
            )}
            {user?.rol === 'trabajador' && (
              <button className="btn btn-secondary" type="button" onClick={() => openModal('password')}>
                Cambiar contraseña
              </button>
            )}
            {(user?.rol === 'admin' || user?.rol === 'empleador') && (
              <>
                <button className="btn btn-secondary" type="button" onClick={handleSyncAll}>
                  Sincronizar
                </button>
                <button className="btn btn-primary" type="button" onClick={() => openModal(section === 'personas' ? 'persona' : section === 'turnos' ? 'turno' : section === 'asignaciones' ? 'asignacion' : section === 'usuarios' ? 'usuario' : 'erp')}>
                  Acción rápida
                </button>
              </>
            )}
            {user && (
              <>
                <div className="user-pill">
                  <div className="user-pill-avatar">{user.nombre.charAt(0).toUpperCase()}</div>
                  <div className="user-pill-meta">
                    <span className="user-pill-name">{user.nombre}</span>
                    <span className="user-pill-role">{user.rol}</span>
                  </div>
                </div>
                <button className="logout-btn" type="button" onClick={logout}>
                  Salir
                </button>
              </>
            )}
          </div>
        </header>

        <section className="hero">
          <div className="panel hero-main">
            <div className="split-row" style={{ alignItems: 'start' }}>
              <div style={{ maxWidth: 720 }}>
                <span className="eyebrow">{user?.rol === 'trabajador' ? 'Mi asistencia' : 'Panel general'}</span>
                <h2 className="page-title" style={{ fontSize: 'clamp(1.7rem, 3vw, 3.1rem)', marginTop: 12 }}>
                  {user?.rol === 'trabajador'
                    ? 'Tus registros de asistencia.'
                    : 'Control de asistencia, biometría y dispositivos en un solo lugar.'}
                </h2>
                <p className="page-subtitle" style={{ marginTop: 12 }}>
                  {user?.rol === 'trabajador'
                    ? 'Revisa tus registros de entrada y salida.'
                    : 'Monitorea la operación diaria, administra el personal y mantén todo sincronizado desde esta plataforma.'}
                </p>
              </div>
            </div>

            {user?.rol !== 'trabajador' && (
            <div className="hero-grid">
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">Marcajes hoy</span>
                  <Badge tone="info">{recentAsistencias.length} recientes</Badge>
                </div>
                <div className="metric-value">{stats.todayCount}</div>
                <div className="metric-foot">{stats.pending} pendientes de sincronización</div>
                <div className="sparkline" aria-hidden>
                  {[20, 34, 28, 50, 46, 64, 41, 72].map((height, index) => (
                    <span key={index} style={{ height: `${height}%` }} />
                  ))}
                </div>
              </article>
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">Personas</span>
                  <Badge tone="success">con datos biométricos</Badge>
                </div>
                <div className="metric-value">{personas.length}</div>
                <div className="metric-foot">{personas.filter((item) => item.huella_id > 0).length} con huella dactilar registrada</div>
                <div className="sparkline" aria-hidden>
                  {[30, 24, 48, 44, 58, 60, 74, 82].map((height, index) => (
                    <span key={index} style={{ height: `${height}%` }} />
                  ))}
                </div>
              </article>
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">Dispositivos</span>
                  <Badge tone={stats.onlineDevices > 0 ? 'success' : 'warning'}>{stats.onlineDevices} en línea</Badge>
                </div>
                <div className="metric-value">{devices.length}</div>
                <div className="metric-foot">{devices.filter(d => d.online).length} en línea · {devices.length} registrados</div>
                <div className="sparkline" aria-hidden>
                  {[68, 62, 58, 71, 64, 78, 85, 72].map((height, index) => (
                    <span key={index} style={{ height: `${height}%` }} />
                  ))}
                </div>
              </article>
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">Verificación biométrica (huella/rostro)</span>
                  <Badge tone="warning">capturas</Badge>
                </div>
                <div className="metric-value">{stats.facialChecks}</div>
                <div className="metric-foot">Marcajes con verificación (huella/rostro)</div>
                <div className="sparkline" aria-hidden>
                  {[16, 28, 18, 46, 38, 52, 48, 66].map((height, index) => (
                    <span key={index} style={{ height: `${height}%` }} />
                  ))}
                </div>
              </article>
            </div>
            )}

          </div>

          {user?.rol !== 'trabajador' && (
          <div className="side-stack">
            <div className="panel status-panel">
              <div className="split-row">
                <div>
                  <h3 className="section-title">Resumen</h3>
                  <p className="section-subtitle">Estado general del sistema</p>
                </div>
                <Badge tone="success">operativo</Badge>
              </div>

              <div className="status-list">
                <div className="status-item">
                  <div className="status-item-left">
                    <span className="dot-online" />
                    <div>
                      <div className="status-name">Plataforma (servidor)</div>
                      <div className="status-meta">Conectado y operativo</div>
                    </div>
                  </div>
                  <Badge tone="success">activo</Badge>
                </div>
                <div className="status-item">
                  <div className="status-item-left">
                    <span className={devices.some(d => d.online) ? 'dot-online' : 'dot-warning'} />
                    <div>
                      <div className="status-name">Dispositivos</div>
                      <div className="status-meta">{devices.filter(d => d.online).length} de {devices.length} en línea</div>
                    </div>
                  </div>
                  <Badge tone={devices.some(d => d.online) ? 'success' : 'warning'}>{devices.filter(d => d.online).length > 0 ? 'conectado' : 'desconectado'}</Badge>
                </div>
                <div className="status-item">
                  <div className="status-item-left">
                    <span className="dot-online" />
                    <div>
                      <div className="status-name">Integraciones</div>
                      <div className="status-meta">{erpList.length} {erpList.length === 1 ? 'conexión activa' : 'conexiones activas'}</div>
                    </div>
                  </div>
                  <Badge tone={erpList.length > 0 ? 'success' : 'info'}>{erpList.length > 0 ? 'conectado' : 'sin configurar'}</Badge>
                </div>
              </div>
            </div>

            <div className="panel quick-panel">
              <div className="split-row">
                <div>
                  <h3 className="section-title">Acciones rápidas</h3>
                  <p className="section-subtitle">Tareas frecuentes</p>
                </div>
              </div>
              <div className="toolbar" style={{ marginTop: 14 }}>
                <button className="btn btn-secondary" type="button" onClick={() => openModal('persona')}>Nueva persona</button>
                <button className="btn btn-secondary" type="button" onClick={() => openModal('turno')}>Nuevo turno</button>
                <button className="btn btn-secondary" type="button" onClick={() => openModal('asignacion')}>Asignar turno</button>
              </div>
            </div>
          </div>
          )}
        </section>

        {(section === 'dashboard' || section === 'asistencias') && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Asistencias recientes</h2>
                <p className="section-subtitle">Filtra y revisa los registros de asistencia del personal.</p>
              </div>
              <div className="toolbar">
                <button className="btn btn-secondary" type="button" onClick={handleExportCsv}>Exportar CSV</button>
                <Link className="btn btn-secondary" href={sectionPaths.asistencias}>Ver todo</Link>
              </div>
            </div>

            <div className="table-card">
              <div className="toolbar" style={{ marginBottom: 14 }}>
                <div className="field" style={{ minWidth: 180 }}>
                  <label>Fecha</label>
                  <input type="date" value={filterDate} onChange={(event) => setFilterDate(event.target.value)} />
                </div>
                <div className="field" style={{ minWidth: 180 }}>
                  <label>Tipo</label>
                  <select value={filterType} onChange={(event) => setFilterType(event.target.value)}>
                    <option value="">Todos</option>
                    <option value="entrada">Entrada</option>
                    <option value="salida">Salida</option>
                    <option value="colacion_entrada">Colación Entrada</option>
                    <option value="colacion_salida">Colación Salida</option>
                  </select>
                </div>
                <div className="field" style={{ minWidth: 220 }}>
                  <label>Método</label>
                  <select value={filterMethod} onChange={(event) => setFilterMethod(event.target.value)}>
                    <option value="">Todos</option>
                    <option value="huella">Huella dactilar</option>
                    <option value="facial+huella">Rostro + Huella dactilar</option>
                  </select>
                </div>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Nombre</th>
                      <th>Tipo</th>
                      <th>Método</th>
                      <th>Fecha y hora</th>
                      <th>Sync</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAsistencias.length > 0 ? (
                      filteredAsistencias.map((item, index) => (
                        <tr key={item.id}>
                          <td className="mono muted">{item.id || index + 1}</td>
                          <td>{item.nombre}</td>
                          <td>
                            <Badge tone={item.tipo === 'entrada' ? 'success' : item.tipo === 'salida' ? 'warning' : item.tipo === 'colacion_entrada' ? 'info' : 'danger'}>{item.tipo}</Badge>
                          </td>
                          <td>
                            <Badge tone={item.metodo.includes('facial') ? 'info' : 'warning'}>{item.metodo}</Badge>
                          </td>
                          <td className="mono muted">{formatDate(item.fecha_hora)} {formatTime(item.fecha_hora)}</td>
                          <td>
                            <Badge tone={item.sincronizado ? 'success' : 'warning'}>{item.sincronizado ? 'sincronizado' : 'pendiente'}</Badge>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={6}>
                          <div className="empty-state">No hay registros con esos filtros.</div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {section === 'personas' && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Personas</h2>
                <p className="section-subtitle">Administra las personas registradas en el sistema.</p>
              </div>
              <div className="toolbar">
                <button className="btn btn-secondary" type="button" onClick={() => openModal('persona')}>Nueva persona</button>
              </div>
            </div>

            <div className="table-card">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Nombre</th>
                      <th>RUT</th>
                      <th>Email</th>
                      <th>Huella</th>
                      <th>Registro</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {personas.map((item) => (
                      <tr key={item.id}>
                        <td className="mono muted">{item.id}</td>
                        <td>{item.nombre}</td>
                        <td className="mono muted">{item.rut}</td>
                        <td className="muted">{item.email || '—'}</td>
                        <td>
                          <Badge tone={item.huella_id ? 'success' : 'danger'}>{item.huella_id ? `ID ${item.huella_id}` : 'sin huella dactilar'}</Badge>
                        </td>
                        <td className="mono muted">{formatDate(item.fecha_registro)}</td>
                        <td>
                          <div className="toolbar">
                            <button className="btn btn-secondary" type="button" disabled={uploadingRostro} onClick={() => handleRostroUpload(item.id)}>{uploadingRostro ? 'Subiendo...' : 'Rostro'}</button>
                            <button className="btn btn-primary" type="button" onClick={() => openHuellaModal(item.id, item.nombre)}>Huella dactilar</button>
                            <button className="btn btn-danger" type="button" onClick={() => handleDeletePersona(item.id)}>{user?.rol === 'admin' ? 'Eliminar' : 'Desactivar'}</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {section === 'turnos' && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Turnos</h2>
                <p className="section-subtitle">Define los horarios y jornadas de trabajo.</p>
              </div>
              <button className="btn btn-secondary" type="button" onClick={() => openModal('turno')}>Nuevo turno</button>
            </div>

            <div className="table-card">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Nombre</th>
                      <th>Inicio</th>
                      <th>Fin</th>
                      <th>Días</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {turnos.map((item) => (
                      <tr key={item.id}>
                        <td className="mono muted">{item.id}</td>
                        <td>{item.nombre}</td>
                        <td className="mono">{item.inicio}</td>
                        <td className="mono">{item.fin}</td>
                        <td>
                          <div className="days">
                            {item.dias.split('').filter((c) => c !== ',').map((code) => (
                              <span key={code} className="day-chip active">{dayNames[code as keyof typeof dayNames] ?? code}</span>
                            ))}
                          </div>
                        </td>
                        <td>
                          <button className="btn btn-danger" type="button" onClick={() => handleDeleteTurno(item.id)}>Eliminar</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {section === 'asignaciones' && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Asignaciones</h2>
                <p className="section-subtitle">Asigna turnos a las personas de la organización.</p>
              </div>
              <button className="btn btn-secondary" type="button" onClick={() => openModal('asignacion')}>Nueva asignación</button>
            </div>

            <div className="table-card">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Persona</th>
                      <th>Turno</th>
                      <th>Desde</th>
                      <th>Estado</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {asignaciones.map((item) => (
                      <tr key={item.id}>
                        <td className="mono muted">{item.id}</td>
                        <td>{item.persona_nombre}</td>
                        <td>{item.turno_nombre}</td>
                        <td className="mono muted">{formatDate(item.fecha_asignacion)}</td>
                        <td>
                          <Badge tone={item.vigente ? 'success' : 'warning'}>{item.vigente ? 'activo' : 'inactivo'}</Badge>
                        </td>
                        <td>
                          <button className="btn btn-danger" type="button" onClick={() => handleDeleteAsignacion(item.id)}>Eliminar</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {section === 'dispositivos' && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Dispositivos</h2>
                <p className="section-subtitle">Supervisa y administra los dispositivos de registro.</p>
              </div>
              {(user?.rol === 'admin' || user?.rol === 'empleador') && (
                <button className="btn btn-primary" type="button" onClick={() => openModal('dispositivo')}>
                  Agregar dispositivo
                </button>
              )}
            </div>

            {generatedPin && (
              <div className="card" style={{ marginBottom: 18, borderColor: 'var(--primary)', borderLeft: '4px solid var(--primary)', padding: 20 }}>
                <div className="status-row">
                  <div className="status-dot" style={{ background: 'var(--primary)' }} />
                  <div>
                    <div className="device-name" style={{ fontWeight: 700, fontSize: '1.1rem' }}>PIN de registro generado</div>
                    <div className="device-ip">Copia este código para configurar el dispositivo físico</div>
                  </div>
                </div>
                <div className="mono" style={{ marginTop: 16, padding: 16, borderRadius: 'var(--radius-md)', background: '#f8fafc', border: '1px solid var(--line)', fontSize: '1.8rem', textAlign: 'center', letterSpacing: '0.3em', fontWeight: 700, color: 'var(--primary)' }}>
                  {generatedPin}
                </div>
                <div className="muted" style={{ marginTop: 12, fontSize: '0.82rem' }}>
                  1. Enciende el dispositivo · 2. Conéctate a su red WiFi (inalámbrica) · 3. Ingresa el PIN y la dirección del servidor (URL) · 4. El dispositivo se configurará automáticamente
                </div>
              </div>
            )}

            <div className="device-grid">
              {dashboardDevices.map((item) => (
                <article className="device-card" key={item.id}>
                  <div className="device-head">
                    <div style={{ flex: 1, minWidth: 0 }}>
                      {editingDeviceId === item.id ? (
                        <div className="status-row" style={{ gap: 8 }}>
                          <input
                            className="input"
                            value={editDeviceName}
                            onChange={(event) => setEditDeviceName(event.target.value)}
                            onKeyDown={(event) => { if (event.key === 'Enter') handleUpdateDeviceName(item.id); }}
                            placeholder="Nombre del dispositivo"
                            autoFocus
                            style={{ flex: 1, fontSize: '0.9rem' }}
                          />
                          <button className="btn btn-primary" type="button" onClick={() => handleUpdateDeviceName(item.id)}>Guardar</button>
                          <button className="btn btn-secondary" type="button" onClick={() => setEditingDeviceId(null)}>Cancelar</button>
                        </div>
                      ) : (
                        <>
                          <div className="status-row" style={{ gap: 10 }}>
                            <span className={`live-dot ${item.online ? 'online' : 'offline'}`} />
                            <div>
                              <div className="device-name">{item.nombre}</div>
                              {item.ip && item.ip !== '—' ? (
                                <>
                                  <a
                                    href={`http://${item.ip}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="device-ip-link"
                                    title="Abrir configuración del dispositivo (misma red)"
                                  >
                                    {item.ip}
                                  </a>
                                  <div className="device-ip-hint">Requiere misma red WiFi</div>
                                </>
                              ) : (
                                <div className="device-ip">IP no disponible</div>
                              )}
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                    <div className="status-row" style={{ gap: 6 }}>
                      <Badge tone={item.online ? 'success' : 'warning'}>{item.online ? 'en línea' : 'desconectado'}</Badge>
                      {item.tienePassword ? (
                        <span title={item.passwordPendiente ? 'Contraseña pendiente de aplicar en el dispositivo' : 'Con contraseña'} style={{ fontSize: '1.1rem' }}>
                          {item.passwordPendiente ? '🔑' : '🔒'}
                        </span>
                      ) : (
                        <span title="Sin contraseña" style={{ fontSize: '1.1rem', opacity: 0.5 }}>🔓</span>
                      )}
                    </div>
                  </div>

                  {item.codigoEnrol && (
                    <div className="card" style={{ marginTop: 12, padding: '10px 14px', borderLeft: '4px solid var(--primary)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span className="muted" style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>PIN de registro</span>
                        <button
                          className="btn btn-secondary"
                          type="button"
                          style={{ fontSize: '0.7rem', padding: '2px 10px' }}
                          onClick={() => {
                            const el = document.getElementById(`pin-${item.id}`) as HTMLSpanElement | null;
                            const btn = document.getElementById(`pin-btn-${item.id}`) as HTMLButtonElement | null;
                            if (el && btn) {
                              if (el.dataset.revealed === 'true') {
                                el.textContent = '••••••';
                                el.dataset.revealed = 'false';
                                btn.textContent = 'Mostrar';
                              } else {
                                el.textContent = item.codigoEnrol!;
                                el.dataset.revealed = 'true';
                                btn.textContent = 'Ocultar';
                              }
                            }
                          }}
                        >
                          Mostrar
                        </button>
                      </div>
                      <span
                        id={`pin-${item.id}`}
                        data-revealed="false"
                        style={{ fontSize: '1.4rem', letterSpacing: '4px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--primary)', marginTop: 6, display: 'inline-block', cursor: 'pointer', userSelect: 'all' }}
                        onClick={() => {
                          const el = document.getElementById(`pin-${item.id}`) as HTMLSpanElement | null;
                          const btn = document.getElementById(`pin-btn-${item.id}`) as HTMLButtonElement | null;
                          if (el && btn) {
                            if (el.dataset.revealed === 'true') {
                              el.textContent = '••••••';
                              el.dataset.revealed = 'false';
                              btn.textContent = 'Mostrar';
                            } else {
                              el.textContent = item.codigoEnrol!;
                              el.dataset.revealed = 'true';
                              btn.textContent = 'Ocultar';
                            }
                          }
                        }}
                      >
                        ••••••
                      </span>
                    </div>
                  )}

                  <div className="device-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', marginTop: 16 }}>
                    <div className="card">
                      <div className="muted">Estado</div>
                      <div className="metric-value" style={{ fontSize: '1.6rem', marginTop: 8, color: item.online ? 'var(--success)' : 'var(--muted)' }}>{item.online ? 'En línea' : 'Desconectado'}</div>
                    </div>
                    <div className="card">
                      <div className="muted">Última conexión</div>
                      <div className="metric-value" style={{ fontSize: '1rem', marginTop: 8, fontFamily: 'var(--font-mono)' }}>
                        {item.ultimoHeartbeat ? formatDate(item.ultimoHeartbeat) + ' ' + formatTime(item.ultimoHeartbeat) : '—'}
                      </div>
                    </div>
                  </div>

                  <div className="device-actions">
                    <button className="btn btn-secondary" type="button" onClick={() => { setEditingDeviceId(item.id); setEditDeviceName(item.nombre); }}>Renombrar</button>
                    {item.ip && item.ip !== '—' && (
                      <a className="btn btn-primary" href={`http://${item.ip}`} target="_blank" rel="noreferrer" title="Abrir panel del dispositivo (requiere misma red WiFi)">Abrir dispositivo</a>
                    )}
                    <button
                      className="btn btn-secondary"
                      type="button"
                      disabled={generatingPasswordFor === item.id}
                      onClick={() => handleGenerarPassword(item.id, item.nombre, !!item.tienePassword)}
                    >
                      {generatingPasswordFor === item.id ? 'Generando...' : item.tienePassword ? 'Regenerar contraseña' : 'Generar contraseña'}
                    </button>
                    {item.tienePassword && (
                      <button className="btn btn-secondary" type="button" onClick={() => handleEliminarPassword(item.id, item.nombre)}>
                        Quitar contraseña
                      </button>
                    )}
                    <a className="btn btn-secondary" href={`http://${item.ip || deviceBase}/registros`} target="_blank" rel="noreferrer">Registros</a>
                    <button className="btn btn-secondary" type="button" onClick={() => handleDeviceSync(item.ip)}>Sincronizar</button>
                    <button
                      className="btn btn-secondary"
                      type="button"
                      disabled={!item.online}
                      onClick={() => handleReiniciarDispositivo(item.id, item.nombre)}
                    >
                      Reiniciar
                    </button>
                    <button
                      className="btn btn-secondary"
                      type="button"
                      disabled={!item.online}
                      onClick={() => handleReconectarWifiDispositivo(item.id, item.nombre)}
                    >
                      Reconectar WiFi
                    </button>
                    <button className="btn btn-danger" type="button" onClick={() => handleDeleteDispositivo(item.id, item.nombre)}>Eliminar</button>
                  </div>
                </article>
              ))}
                  {dashboardDevices.length === 0 ? <div className="empty-state">No hay dispositivos registrados.</div> : null}
            </div>
          </section>
        )}

        {section === 'duplicados' && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Duplicados pendientes</h2>
                <p className="section-subtitle">Se detectaron personas con el mismo RUT durante el enrolamiento del dispositivo. Selecciona cuál conservar y cuál eliminar para fusionar sus datos biométricos.</p>
              </div>
              <button className="btn btn-secondary" type="button" onClick={() => refreshSection('duplicados')}>Actualizar</button>
            </div>

            {duplicados.length === 0 ? (
              <div className="card" style={{ padding: 24, textAlign: 'center' }}>
                <div style={{ fontSize: '2rem', marginBottom: 8 }}>✓</div>
                <div style={{ fontWeight: 600 }}>No hay duplicados pendientes</div>
                <div className="muted" style={{ marginTop: 4 }}>Todos los registros están consolidados.</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {duplicados.map((dup) => (
                  <div key={dup.id} className="card" style={{ padding: 24 }}>
                    <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                      {/* Persona a mantener */}
                      <div style={{ flex: 1, minWidth: 250, padding: 16, borderRadius: 'var(--radius-md)', background: '#f0fdf4', border: '2px solid #86efac' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                          <Badge tone="success">Conservar (existente)</Badge>
                        </div>
                        <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>{dup.nombre_mantener}</div>
                        <div className="mono muted" style={{ marginTop: 4 }}>RUT: {dup.rut_mantener}</div>
                        <div className="muted" style={{ marginTop: 2, fontSize: '0.82rem' }}>ID: {dup.persona_mantener_id}</div>
                        <div className="muted" style={{ marginTop: 2, fontSize: '0.82rem' }}>Tipo: {dup.tipo_deteccion === 'rut' ? 'Mismo RUT' : 'Mismo rostro'}</div>
                        <button
                          className="btn btn-primary"
                          type="button"
                          style={{ marginTop: 16 }}
                          disabled={mergingPersonas}
                          onClick={async () => {
                            setMergingPersonas(true);
                            const res = await mergePersonas(dup.persona_mantener_id, dup.persona_eliminar_id);
                            setMergingPersonas(false);
                            if (res && 'ok' in res && res.ok) {
                              showToast('success', res.mensaje);
                              pushLog('ok', `Duplicado resuelto: se conservó ${dup.nombre_mantener} (ID ${dup.persona_mantener_id})`);
                              refreshSection('duplicados');
                            } else {
                              showToast('error', 'Error al fusionar personas');
                            }
                          }}
                        >
                          {mergingPersonas ? 'Fusionando...' : 'Mantener esta'}
                        </button>
                      </div>

                      {/* Flecha */}
                      <div style={{ display: 'flex', alignItems: 'center', fontSize: '1.5rem', color: 'var(--muted)' }}>→</div>

                      {/* Persona a eliminar */}
                      <div style={{ flex: 1, minWidth: 250, padding: 16, borderRadius: 'var(--radius-md)', background: '#fef2f2', border: '2px solid #fca5a5' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                          <Badge tone="danger">Eliminar (huérfana)</Badge>
                        </div>
                        <div style={{ fontWeight: 600, fontSize: '1.1rem' }}>{dup.nombre_eliminar}</div>
                        <div className="mono muted" style={{ marginTop: 4 }}>RUT: {dup.rut_eliminar}</div>
                        <div className="muted" style={{ marginTop: 2, fontSize: '0.82rem' }}>ID: {dup.persona_eliminar_id}</div>
                        <div className="muted" style={{ marginTop: 2, fontSize: '0.82rem' }}>Registrada desde el dispositivo</div>
                        <button
                          className="btn btn-primary"
                          type="button"
                          style={{ marginTop: 16 }}
                          disabled={mergingPersonas}
                          onClick={async () => {
                            setMergingPersonas(true);
                            const res = await mergePersonas(dup.persona_eliminar_id, dup.persona_mantener_id);
                            setMergingPersonas(false);
                            if (res && 'ok' in res && res.ok) {
                              showToast('success', res.mensaje);
                              pushLog('ok', `Duplicado resuelto: se conservó ${dup.nombre_eliminar} (ID ${dup.persona_eliminar_id})`);
                              refreshSection('duplicados');
                            } else {
                              showToast('error', 'Error al fusionar personas');
                            }
                          }}
                        >
                          {mergingPersonas ? 'Fusionando...' : 'Mantener esta'}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {section === 'erp' && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Integraciones (ERP)</h2>
                <p className="section-subtitle">Conecta el sistema con tus plataformas externas.</p>
              </div>
              <button className="btn btn-secondary" type="button" onClick={() => openModal('erp')}>Agregar integración</button>
            </div>

            <div className="erp-grid">
              {erpList.map((item) => (
                <article className="erp-card" key={item.id}>
                  <div className="erp-head">
                    <div className="erp-logo">⌁</div>
                    <div>
                      <div className="device-name">{item.nombre}</div>
                      <div className="device-ip">{item.tipo}</div>
                    </div>
                    <Badge tone={item.activo ? 'success' : 'warning'}>{item.activo ? 'activo' : 'inactivo'}</Badge>
                  </div>
                  <div className="muted" style={{ marginTop: 14, wordBreak: 'break-word' }}>{item.webhookUrl}</div>
                  {item.ultimoEstado && (
                    <div className="muted" style={{ marginTop: 8, fontSize: '0.82rem' }}>
                      Último envío: {item.ultimoEnvio ? new Date(item.ultimoEnvio).toLocaleString() : '—'} · {item.ultimoEstado}
                    </div>
                  )}
                  <div className="device-actions" style={{ marginTop: 16 }}>
                    <button className="btn btn-primary" type="button" onClick={() => handleEnviarErp(item.id, item.nombre)}>Enviar</button>
                    <button className="btn btn-secondary" type="button" onClick={() => handleTestErp(item.id, item.nombre)}>Test</button>
                    <button className="btn btn-danger" type="button" onClick={() => handleDeleteErp(item.id)}>Eliminar</button>
                  </div>
                </article>
              ))}
              {erpList.length === 0 ? <div className="empty-state">No hay integraciones configuradas.</div> : null}
            </div>
          </section>
        )}

        {section === 'logs' && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Registro de eventos</h2>
                <p className="section-subtitle">Historial de eventos y operaciones del sistema.</p>
              </div>
              <div className="toolbar">
                <select value={logFilter} onChange={(event) => setLogFilter(event.target.value as typeof logFilter)}>
                  <option value="all">Todos</option>
                  <option value="ok">Exitosos</option>
                  <option value="err">Errores</option>
                  <option value="info">Info</option>
                  <option value="warn">Advertencias</option>
                </select>
                <button className="btn btn-secondary" type="button" onClick={handleClearLogs}>Limpiar</button>
              </div>
            </div>

            <div className="grid-2">
              <div className="log-box">
                {visibleLogs.length > 0 ? (
                  visibleLogs.map((item) => (
                    <div className="log-line" key={item.id}>
                      <span className="log-time">{item.time}</span>
                      <span className={`log-${item.type}`}>{item.message}</span>
                    </div>
                  ))
                ) : (
                  <div className="empty-state">No hay logs con este filtro.</div>
                )}
              </div>

              <div className="card">
                <h3 className="section-title">Información del sistema</h3>
                <p className="section-subtitle">Resumen de la configuración actual.</p>
                <div className="status-list" style={{ marginTop: 16 }}>
                  <div className="status-item">
                    <div>
                      <div className="status-name">Personas registradas</div>
                      <div className="status-meta">{personas.length} en total</div>
                    </div>
                  </div>
                  <div className="status-item">
                    <div>
                      <div className="status-name">Dispositivos activos</div>
                      <div className="status-meta">{devices.filter(d => d.online).length} en línea de {devices.length}</div>
                    </div>
                  </div>
                  <div className="status-item">
                    <div>
                      <div className="status-name">Integraciones activas</div>
                      <div className="status-meta">{erpList.length} configuradas</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {section === 'usuarios' && user?.rol === 'trabajador' && personaActual && (
          <section className="section">
            <div className="section-head">
              <div>
                <h3 className="section-title">Mi cuenta</h3>
                <p className="section-subtitle">Información personal, consentimiento de datos biométricos y registro de rostro.</p>
              </div>
            </div>

            <div className="profile-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 24 }}>
              <div className="card" style={{ padding: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 20 }}>
                  <div>
                    <h4 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Información personal</h4>
                    <p style={{ fontSize: 13, color: '#64748b', margin: '4px 0 0' }}>Tus datos registrados en el sistema.</p>
                  </div>
                  <div style={{ width: 48, height: 48, borderRadius: 12, background: '#1d4ed8', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, fontWeight: 700, flexShrink: 0 }}>
                    {personaActual.nombre.charAt(0).toUpperCase()}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div><span style={{ fontSize: 12, color: '#64748b', display: 'block' }}>Nombre completo</span><span style={{ fontSize: 15, fontWeight: 500 }}>{personaActual.nombre}</span></div>
                  <div><span style={{ fontSize: 12, color: '#64748b', display: 'block' }}>RUT</span><span style={{ fontSize: 15, fontWeight: 500 }}>{personaActual.rut || '—'}</span></div>
                  <div><span style={{ fontSize: 12, color: '#64748b', display: 'block' }}>Email</span><span style={{ fontSize: 15, fontWeight: 500 }}>{personaActual.email || '—'}</span></div>
                  <div><span style={{ fontSize: 12, color: '#64748b', display: 'block' }}>Registrado desde</span><span style={{ fontSize: 15, fontWeight: 500 }}>{personaActual.fecha_registro ? formatDate(personaActual.fecha_registro) : '—'}</span></div>
                  <div><span style={{ fontSize: 12, color: '#64748b', display: 'block' }}>Huella</span><span style={{ fontSize: 15, fontWeight: 500 }}>{personaActual.huella_id ? 'Registrada' : 'No registrada'}</span></div>
                </div>
              </div>

              <div className="card" style={{ padding: 24 }}>
                <h4 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Consentimiento de datos biométricos</h4>
                <p style={{ fontSize: 13, color: '#64748b', margin: '8px 0 0' }}>Debes aceptar el consentimiento antes de registrar tus datos faciales.</p>
                <div style={{ marginTop: 24, display: 'flex', alignItems: 'center', gap: 12 }}>
                  <label style={{ position: 'relative', display: 'inline-block', width: 48, height: 26, cursor: guardandoConsentimiento ? 'not-allowed' : 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={consentimientoActivo}
                      disabled={guardandoConsentimiento}
                      onChange={handleToggleConsentimiento}
                      style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }}
                    />
                    <span style={{
                      position: 'absolute', inset: 0, borderRadius: 26, transition: 'background .2s',
                      background: consentimientoActivo ? '#1d4ed8' : '#cbd5e1'
                    }}>
                      <span style={{
                        position: 'absolute', left: consentimientoActivo ? 24 : 2, top: 2, width: 22, height: 22,
                        borderRadius: '50%', background: '#fff', transition: 'left .2s', boxShadow: '0 1px 3px rgba(0,0,0,.15)'
                      }} />
                    </span>
                  </label>
                  <span style={{ fontSize: 14, color: '#334155', fontWeight: 500 }}>
                    {consentimientoActivo ? 'Consentimiento otorgado' : 'Consentimiento no otorgado'}
                  </span>
                </div>
                {guardandoConsentimiento && <p style={{ fontSize: 13, color: '#64748b', marginTop: 8 }}>Guardando...</p>}
              </div>

              <div className="card" style={{ padding: 24 }}>
                <h4 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Registro facial</h4>
                <p style={{ fontSize: 13, color: '#64748b', margin: '8px 0 0' }}>Captura tu rostro para habilitar el reconocimiento por cámara.</p>
                <button
                  className="btn btn-primary"
                  type="button"
                  disabled={!consentimientoActivo}
                  onClick={() => {
                    setRostroPersonaId(personaActual.id);
                    setWebcamActive(true);
                    setCapturedImage(null);
                  }}
                  style={{ marginTop: 24, opacity: consentimientoActivo ? 1 : 0.5 }}
                >
                  {personaActual.encoding_facial ? 'Actualizar rostro' : 'Registrar rostro'}
                </button>
                {!consentimientoActivo && (
                  <p style={{ fontSize: 12, color: '#dc2626', marginTop: 8 }}>Debes otorgar consentimiento biométrico primero.</p>
                )}
              </div>

              <div className="card" style={{ padding: 24 }}>
                <h4 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Estado de datos biométricos</h4>
                <p style={{ fontSize: 13, color: '#64748b', margin: '8px 0 0' }}>Estado actual de tus datos biométricos en el sistema.</p>
                <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#f8fafc', borderRadius: 8 }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 500 }}>Datos faciales</div>
                      <div style={{ fontSize: 12, color: '#64748b' }}>Codificación biométrica</div>
                    </div>
                    <Badge tone={personaActual.encoding_facial ? 'success' : 'warning'}>
                      {personaActual.encoding_facial ? 'Registrado' : 'No registrado'}
                    </Badge>
                  </div>
                  {personaActual.encoding_facial && (
                    <button
                      className="btn btn-danger"
                      type="button"
                      disabled={eliminandoBiometricos}
                      onClick={handleEliminarBiometricos}
                    >
                      {eliminandoBiometricos ? 'Eliminando...' : 'Eliminar datos biométricos'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </section>
        )}
        {section === 'usuarios' && user?.rol !== 'trabajador' && (
          <section className="section">
            <div className="section-head">
              <div>
                <h3 className="section-title">Usuarios del sistema</h3>
                <p className="section-subtitle">Administra los usuarios del sistema y sus permisos.</p>
              </div>
              <div className="toolbar">
                <button className="btn btn-secondary" type="button" onClick={() => openModal('password')}>
                  Cambiar contraseña
                </button>
                <button className="btn btn-primary" type="button" onClick={() => openModal('usuario')}>
                  Nuevo usuario
                </button>
              </div>
            </div>

            <div className="table-card">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Email</th>
                      {user?.rol === 'admin' && <th>Empresa</th>}
                      <th>Rol</th>
                      <th>Activo</th>
                      <th>Creado</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usuarios.map((item) => (
                      <tr key={`${item.id}-${item.empresa_id}`}>
                        <td>{item.nombre}</td>
                        <td className="mono muted">{item.email}</td>
                        {user?.rol === 'admin' && <td>{item.empresa_nombre}</td>}
                        <td>
                          <Badge tone={item.rol === 'admin' ? 'danger' : item.rol === 'empleador' ? 'warning' : 'info'}>
                            {item.rol === 'admin' ? 'Admin sistema' : item.rol === 'empleador' ? 'Admin empresa' : 'Trabajador'}
                          </Badge>
                        </td>
                        <td>{item.activo ? 'Sí' : 'No'}</td>
                        <td className="mono muted">{item.created_at ? formatDate(item.created_at) : '—'}</td>
                        <td>
                          <button className="btn btn-ghost" type="button" onClick={() => handleEditUsuario(item)} style={{ marginRight: 8 }}>
                            Editar
                          </button>
                          {(user?.rol === 'admin' || (user?.rol === 'empleador' && (item.rol === 'empleador' || item.rol === 'trabajador'))) && item.id !== user?.id && (
                            <button className="btn btn-danger" type="button" onClick={() => handleDeleteUsuario(item.id, item.empresa_id, item.nombre)}>
                              Eliminar
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {usuarios.length === 0 && (
                      <tr>
                        <td colSpan={user?.rol === 'admin' ? 7 : 6} className="empty-state">No hay usuarios registrados.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {section === 'empresas' && user?.rol === 'admin' && (
          <section className="section">
            <div className="section-head">
              <div>
                <h3 className="section-title">Empresas registradas</h3>
                <p className="section-subtitle">Cada empresa opera con sus propios datos y configuraciones.</p>
              </div>
              <div className="toolbar">
                <button className="btn btn-primary" type="button" onClick={() => openModal('empresa')}>
                  Nueva empresa
                </button>
              </div>
            </div>

            <div className="table-card">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Nombre</th>
                      <th>RUT</th>
                      <th>Email</th>
                      <th>Teléfono</th>
                      <th>Creada</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {empresas.map((item) => (
                      <tr key={item.id}>
                        <td className="mono muted">{item.id}</td>
                        <td>{item.nombre}</td>
                        <td className="mono">{item.rut_empresa || '—'}</td>
                        <td className="mono muted">{item.email_contacto || '—'}</td>
                        <td>{item.telefono || '—'}</td>
                        <td className="mono muted">{item.created_at ? formatDate(item.created_at) : '—'}</td>
                        <td>
                          {item.id !== 1 && (
                            <button className="btn btn-danger" type="button" onClick={() => handleDeleteEmpresa(item.id, item.nombre)}>
                              Eliminar
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {empresas.length === 0 && (
                      <tr>
                        <td colSpan={7} className="empty-state">No hay empresas registradas.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}
      </main>

      {modal === 'empresa' && (
        <div className="overlay" onClick={closeModal} role="presentation">
          <div className="modal" onClick={(e) => e.stopPropagation()} role="presentation">
            <div className="modal-head">
              <h3 className="modal-title">Nueva empresa</h3>
              <p className="modal-subtitle">Registra una nueva empresa y asígnale un usuario administrador.</p>
            </div>
            <div className="modal-body">
              {formError && <div className="login-error" style={{ marginBottom: 12 }}>{formError}</div>}
              <div className="field">
                <label>Nombre de la empresa *</label>
                <input type="text" placeholder="Ej: Constructora XYZ S.A." value={empresaForm.nombre} onChange={(e) => setEmpresaForm((c) => ({ ...c, nombre: e.target.value }))} />
              </div>
              <div className="field">
                <label>RUT empresa</label>
                <input type="text" placeholder="Ej: 76123456-7" value={empresaForm.rut_empresa} onChange={(e) => setEmpresaForm((c) => ({ ...c, rut_empresa: e.target.value }))} />
              </div>
              <div className="field">
                <label>Email contacto</label>
                <input type="email" placeholder="contacto@empresa.cl" value={empresaForm.email_contacto} onChange={(e) => setEmpresaForm((c) => ({ ...c, email_contacto: e.target.value }))} />
              </div>
              <div className="field">
                <label>Teléfono</label>
                <input type="text" placeholder="+56 9 XXXX XXXX" value={empresaForm.telefono} onChange={(e) => setEmpresaForm((c) => ({ ...c, telefono: e.target.value }))} />
              </div>
              <div className="field">
                <label>Dirección</label>
                <input type="text" placeholder="Av. Siempre Viva 742" value={empresaForm.direccion} onChange={(e) => setEmpresaForm((c) => ({ ...c, direccion: e.target.value }))} />
              </div>

              <hr style={{ margin: '16px 0', border: 'none', borderTop: '1px solid var(--border-color, #eee)' }} />
              <p style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: 12 }}>Usuario administrador *</p>

              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <button
                  type="button"
                  className={`btn btn-sm ${empresaUserMode === 'new' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => { setEmpresaUserMode('new'); setFormError(''); }}
                >
                  Crear nuevo
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${empresaUserMode === 'existing' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => { setEmpresaUserMode('existing'); setFormError(''); }}
                >
                  Asignar existente
                </button>
              </div>

              {empresaUserMode === 'new' ? (
                <>
                  <div className="field">
                    <label>Nombre del usuario *</label>
                    <input type="text" placeholder="Ej: Juan Pérez" value={empresaForm.nombre_usuario} onChange={(e) => setEmpresaForm((c) => ({ ...c, nombre_usuario: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Email del usuario *</label>
                    <input type="email" placeholder="admin@empresa.cl" value={empresaForm.email_usuario} onChange={(e) => setEmpresaForm((c) => ({ ...c, email_usuario: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Contraseña *</label>
                    <input type="password" placeholder="Mínimo 4 caracteres" value={empresaForm.password_usuario} onChange={(e) => setEmpresaForm((c) => ({ ...c, password_usuario: e.target.value }))} />
                  </div>
                </>
              ) : (
                <div className="field">
                  <label>Seleccionar usuario *</label>
                  <select
                    value={empresaForm.usuario_existente_id ?? ''}
                    onChange={(e) => setEmpresaForm((c) => ({ ...c, usuario_existente_id: e.target.value ? Number(e.target.value) : undefined }))}
                  >
                    <option value="">-- Selecciona un usuario --</option>
                    {usuarios
                      .filter(u => u.rol === 'empleador')
                      .filter((u, i, arr) => arr.findIndex(x => x.id === u.id) === i)
                      .map((u) => (
                        <option key={u.id} value={u.id}>{u.nombre} ({u.email}) — {u.empresa_nombre}</option>
                      ))}
                  </select>
                </div>
              )}

              <div className="field">
                <label>Rol del usuario</label>
                <select value={empresaForm.rol_usuario} onChange={(e) => setEmpresaForm((c) => ({ ...c, rol_usuario: e.target.value }))}>
                  <option value="empleador">Empleador</option>
                  <option value="trabajador">Trabajador</option>
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" type="button" onClick={handleCreateEmpresa}>Crear empresa</button>
            </div>
          </div>
        </div>
      )}

      {modal === 'usuario' && (
        <div className="overlay" onClick={closeModal} role="presentation">
          <div className="modal" onClick={(e) => e.stopPropagation()} role="presentation">
            <div className="modal-head">
              <h3 className="modal-title">{editingUsuario ? 'Editar usuario' : 'Nuevo usuario'}</h3>
              <p className="modal-subtitle">{editingUsuario ? `Editando a ${editingUsuario.nombre}` : (user?.rol === 'admin' ? 'Crea una cuenta y asígnala a una empresa.' : 'Crea una cuenta de acceso. Se le asigna a tu misma empresa.')}</p>
            </div>
            <div className="modal-body">
              {formError && <div className="login-error" style={{ marginBottom: 12 }}>{formError}</div>}
              <div className="field">
                <label>Nombre completo</label>
                <input
                  type="text"
                  placeholder="Ej: Juan Pérez"
                  value={registerForm.nombre}
                  onChange={(e) => setRegisterForm((c) => ({ ...c, nombre: e.target.value }))}
                />
              </div>
              <div className="field">
                <label>Email</label>
                <input
                  type="email"
                  placeholder="ejemplo@empresa.cl"
                  value={registerForm.email}
                  onChange={(e) => setRegisterForm((c) => ({ ...c, email: e.target.value }))}
                />
              </div>
              <div className="field">
                <label>{editingUsuario ? 'Nueva contraseña (opcional)' : 'Contraseña provisional'}</label>
                <input
                  type="password"
                  placeholder={editingUsuario ? 'Dejar vacío para mantener actual' : 'Mínimo 4 caracteres'}
                  value={registerForm.password}
                  onChange={(e) => setRegisterForm((c) => ({ ...c, password: e.target.value }))}
                />
              </div>
              {user?.rol === 'admin' && empresas.length > 0 && (
                <div className="field">
                  <label>Empresa</label>
                  <select
                    value={registerForm.empresa_id ?? ''}
                    onChange={(e) => setRegisterForm((c) => ({ ...c, empresa_id: Number(e.target.value) }))}
                  >
                    <option value="">Selecciona una empresa</option>
                    {empresas.map((emp) => (
                      <option key={emp.id} value={emp.id}>{emp.nombre}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="field">
                <label>Rol</label>
                <select
                  value={registerForm.rol}
                  onChange={(e) => setRegisterForm((c) => ({ ...c, rol: e.target.value }))}
                  disabled={user?.rol === 'trabajador' && editingUsuario !== null}
                >
                  {(user?.rol === 'admin' || user?.rol === 'empleador') && <option value="empleador">Admin de empresa</option>}
                  <option value="trabajador">Trabajador</option>
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" type="button" onClick={editingUsuario ? handleUpdateUsuario : handleRegisterUser}>
                {editingUsuario ? 'Actualizar' : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {modal === 'password' && (
        <div className="overlay" onClick={closeModal} role="presentation">
          <div className="modal" onClick={(e) => e.stopPropagation()} role="presentation">
            <div className="modal-head">
              <h3 className="modal-title">Cambiar contraseña</h3>
              <p className="modal-subtitle">Actualiza tu clave de acceso al sistema.</p>
            </div>
            <div className="modal-body">
              {formError && <div className="login-error" style={{ marginBottom: 12 }}>{formError}</div>}
              <div className="field">
                <label>Contraseña actual</label>
                <input
                  type="password"
                  placeholder="Tu contraseña actual"
                  value={passwordForm.passwordActual}
                  onChange={(e) => setPasswordForm((c) => ({ ...c, passwordActual: e.target.value }))}
                />
              </div>
              <div className="field">
                <label>Contraseña nueva</label>
                <input
                  type="password"
                  placeholder="Mínimo 4 caracteres"
                  value={passwordForm.passwordNueva}
                  onChange={(e) => setPasswordForm((c) => ({ ...c, passwordNueva: e.target.value }))}
                />
              </div>
              <div className="field">
                <label>Confirmar contraseña</label>
                <input
                  type="password"
                  placeholder="Repite la nueva contraseña"
                  value={passwordForm.confirmacion}
                  onChange={(e) => setPasswordForm((c) => ({ ...c, confirmacion: e.target.value }))}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" type="button" onClick={handleChangePassword}>Actualizar</button>
            </div>
          </div>
        </div>
      )}

      {modal === 'dispositivo' && (
        <div className="overlay" onClick={closeModal} role="presentation">
          <div className="modal" onClick={(e) => e.stopPropagation()} role="presentation">
            <div className="modal-head">
              <h3 className="modal-title">Agregar dispositivo</h3>
              <p className="modal-subtitle">Genera un PIN de registro para configurar un nuevo dispositivo.</p>
            </div>
            <div className="modal-body">
              {formError && <div className="login-error" style={{ marginBottom: 12 }}>{formError}</div>}
              <div className="field">
                <label>Nombre del dispositivo *</label>
                <input
                  type="text"
                  placeholder="Ej: Reloj entrada principal"
                  value={deviceForm.nombre}
                  onChange={(e) => setDeviceForm((c) => ({ ...c, nombre: e.target.value }))}
                />
              </div>
              {generatedPin && (
                <div className="card" style={{ marginTop: 16, borderColor: 'var(--primary)', borderLeft: '4px solid var(--primary)', padding: 16 }}>
                  <div className="status-row">
                    <div className="status-dot" style={{ background: 'var(--primary)' }} />
                    <div>
                      <div className="device-name" style={{ fontWeight: 700 }}>PIN generado</div>
                      <div className="device-ip">Copia este código para configurar el dispositivo</div>
                    </div>
                  </div>
                  <div className="mono" style={{ marginTop: 12, padding: 12, borderRadius: 'var(--radius-md)', background: '#f8fafc', border: '1px solid var(--line)', fontSize: '1.5rem', textAlign: 'center', letterSpacing: '0.3em', fontWeight: 700, color: 'var(--primary)' }}>
                    {generatedPin}
                  </div>
                  <div className="muted" style={{ marginTop: 12, fontSize: '0.82rem' }}>
                  1. Enciende el dispositivo · 2. Conéctate a su red WiFi (inalámbrica) · 3. Ingresa el PIN y la dirección del servidor (URL) · 4. El dispositivo se configurará automáticamente
                  </div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeModal}>Cerrar</button>
              <button className="btn btn-primary" type="button" onClick={handleGenerarPin}>Generar PIN</button>
            </div>
          </div>
        </div>
      )}

      {generatedDevicePassword && (
        <div className="overlay" onClick={() => setGeneratedDevicePassword(null)} role="presentation">
          <div className="modal" onClick={(e) => e.stopPropagation()} role="presentation">
            <div className="modal-head">
              <h3 className="modal-title">Contraseña generada</h3>
              <p className="modal-subtitle">Guarde esta contraseña. Solo se muestra una vez.</p>
            </div>
            <div className="modal-body">
              <div className="card" style={{ borderColor: 'rgba(217, 119, 6, 0.3)', borderLeft: '4px solid var(--warning)', background: 'var(--warning-light)', padding: 14, marginBottom: 16 }}>
                <strong style={{ color: 'var(--warning)' }}>Guarde esta contraseña. Solo se muestra una vez.</strong>
              </div>
              <div className="mono" style={{ padding: 16, borderRadius: 'var(--radius-md)', background: '#f8fafc', border: '1px solid var(--line)', fontSize: '1.6rem', textAlign: 'center', letterSpacing: '0.25em', fontWeight: 700, color: 'var(--primary)' }}>
                {generatedDevicePassword}
              </div>
              <div className="muted" style={{ marginTop: 16, fontSize: '0.82rem' }}>
                1. El dispositivo aplicará la contraseña cuando se conecte a la plataforma (servidor).<br />
                2. Si está desconectado, ingrésela manualmente en la configuración WiFi del dispositivo.<br />
                3. Use esta contraseña para acceder a la configuración del dispositivo.
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={() => setGeneratedDevicePassword(null)}>Cerrar</button>
              <button className="btn btn-primary" type="button" onClick={() => {
                navigator.clipboard.writeText(generatedDevicePassword);
                showToast('success', 'Contrasena copiada al portapapeles');
              }}>Copiar</button>
            </div>
          </div>
        </div>
      )}

      {modal === 'persona' && (
        <div className="overlay" onClick={closeModal} role="presentation">
          <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Nueva persona">
            <div className="modal-head">
              <div>
                <span className="eyebrow">Registro</span>
                <h3 className="modal-title">Nueva persona</h3>
                <p className="section-subtitle">Registra una nueva persona para control de asistencia.</p>
              </div>
              <button className="btn btn-ghost" type="button" onClick={closeModal}>Cerrar</button>
            </div>
            <div className="modal-body">
              <div className="form-row">
                <div className="field">
                  <label>Nombre completo</label>
                  <input value={personaForm.nombre} onChange={(event) => setPersonaForm((current) => ({ ...current, nombre: event.target.value }))} placeholder="Juan Pérez" />
                </div>
                <div className="field">
                  <label>RUT</label>
                  <input value={personaForm.rut} onChange={(event) => setPersonaForm((current) => ({ ...current, rut: event.target.value }))} placeholder="12345678-9" />
                </div>
              </div>
              <div className="field">
                <label>Email</label>
                <input value={personaForm.email} onChange={(event) => setPersonaForm((current) => ({ ...current, email: event.target.value }))} placeholder="juan@empresa.cl" />
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', margin: '14px 0', padding: '10px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '6px' }}>
                <input type="checkbox" id="consent-check" checked={personaForm.consentimiento}
                  onChange={(event) => setPersonaForm((current) => ({ ...current, consentimiento: event.target.checked }))}
                  style={{ marginTop: '2px', width: '16px', height: '16px', flexShrink: 0, accentColor: 'var(--primary)' }} />
                <label htmlFor="consent-check" style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: '1.4', cursor: 'pointer' }}>
                  Acepto la política de privacidad y el tratamiento de datos biométricos para el control de asistencia
                </label>
              </div>
              {formError ? <div className="badge danger">{formError}</div> : null}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" type="button" onClick={handleCreatePersona}>Registrar persona</button>
            </div>
          </div>
        </div>
      )}

      {modal === 'turno' && (
        <div className="overlay" onClick={closeModal} role="presentation">
          <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Nuevo turno">
            <div className="modal-head">
              <div>
                <span className="eyebrow">Calendario</span>
                <h3 className="modal-title">Nuevo turno</h3>
                <p className="section-subtitle">Define nombre, horario y días activos en una sola vista.</p>
              </div>
              <button className="btn btn-ghost" type="button" onClick={closeModal}>Cerrar</button>
            </div>
            <div className="modal-body">
              <div className="field">
                <label>Nombre del turno</label>
                <input value={turnoForm.nombre} onChange={(event) => setTurnoForm((current) => ({ ...current, nombre: event.target.value }))} placeholder="Turno Mañana" />
              </div>
              <div className="form-row">
                <div className="field">
                  <label>Hora inicio</label>
                  <input type="time" value={turnoForm.inicio} onChange={(event) => setTurnoForm((current) => ({ ...current, inicio: event.target.value }))} />
                </div>
                <div className="field">
                  <label>Hora fin</label>
                  <input type="time" value={turnoForm.fin} onChange={(event) => setTurnoForm((current) => ({ ...current, fin: event.target.value }))} />
                </div>
              </div>
              <div className="field">
                <label>Días activos</label>
                <div className="days">
                  {dayCodes.map((code) => (
                    <button
                      key={code}
                      className={`day-chip ${days.includes(code) ? 'active' : ''}`}
                      type="button"
                      onClick={() => {
                        setDays((current) => (current.includes(code) ? current.filter((item) => item !== code) : [...current, code]));
                      }}
                    >
                      {dayNames[code]}
                    </button>
                  ))}
                </div>
              </div>
              <div className="field" style={{ marginTop: 12 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input type="checkbox" checked={turnoForm.con_colacion}
                    onChange={(event) => setTurnoForm((current) => ({ ...current, con_colacion: event.target.checked }))} />
                  ¿Tiene colación?
                </label>
              </div>
              {turnoForm.con_colacion && (
                <div className="form-row">
                  <div className="field">
                    <label>Colación inicio</label>
                    <input type="time" value={turnoForm.colacion_inicio} onChange={(event) => setTurnoForm((current) => ({ ...current, colacion_inicio: event.target.value }))} />
                  </div>
                  <div className="field">
                    <label>Colación fin</label>
                    <input type="time" value={turnoForm.colacion_fin} onChange={(event) => setTurnoForm((current) => ({ ...current, colacion_fin: event.target.value }))} />
                  </div>
                </div>
              )}
              {formError ? <div className="badge danger">{formError}</div> : null}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" type="button" onClick={handleCreateTurno}>Crear turno</button>
            </div>
          </div>
        </div>
      )}

      {modal === 'asignacion' && (
        <div className="overlay" onClick={closeModal} role="presentation">
          <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Nueva asignación">
            <div className="modal-head">
              <div>
                <span className="eyebrow">Control</span>
                <h3 className="modal-title">Asignar turno</h3>
                <p className="section-subtitle">Vincula una persona con un turno operativo.</p>
              </div>
              <button className="btn btn-ghost" type="button" onClick={closeModal}>Cerrar</button>
            </div>
            <div className="modal-body">
              <div className="field">
                <label>Persona</label>
                <select value={asignacionForm.rut} onChange={(event) => setAsignacionForm((current) => ({ ...current, rut: event.target.value }))}>
                  <option value="">Selecciona una persona</option>
                  {personas.map((item) => (
                    <option value={item.rut} key={item.id}>
                      {item.nombre} - {item.rut}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Turno</label>
                <select value={asignacionForm.turnoId} onChange={(event) => setAsignacionForm((current) => ({ ...current, turnoId: event.target.value }))}>
                  <option value="">Selecciona un turno</option>
                  {turnos.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.nombre} ({item.inicio} - {item.fin})
                    </option>
                  ))}
                </select>
              </div>
              {formError ? <div className="badge danger">{formError}</div> : null}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" type="button" onClick={handleCreateAsignacion}>Asignar</button>
            </div>
          </div>
        </div>
      )}

      {modal === 'erp' && (
        <div className="overlay" onClick={closeModal} role="presentation">
          <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Nueva integración ERP">
            <div className="modal-head">
              <div>
                <span className="eyebrow">Integraciones</span>
                <h3 className="modal-title">Nueva integración ERP</h3>
                <p className="section-subtitle">Configura la conexión con tu sistema externo.</p>
              </div>
              <button className="btn btn-ghost" type="button" onClick={closeModal}>Cerrar</button>
            </div>
            <div className="modal-body">
              <div className="form-row">
                <div className="field">
                  <label>Nombre</label>
                  <input value={erpForm.nombre} onChange={(event) => setErpForm((current) => ({ ...current, nombre: event.target.value }))} placeholder="Odoo Empresa" />
                </div>
                <div className="field">
                  <label>Tipo</label>
                  <select value={erpForm.tipo} onChange={(event) => handleErpTypeChange(event.target.value as keyof typeof erpPresets)}>
                    <option value="generic">Genérico / Webhook</option>
                    <option value="odoo">Odoo</option>
                    <option value="defontana">Defontana</option>
                    <option value="buk">Buk / Talana</option>
                    <option value="sap">SAP</option>
                  </select>
                </div>
              </div>

              <div className="field">
                <label>URL del endpoint</label>
                <input value={erpForm.webhookUrl} onChange={(event) => setErpForm((current) => ({ ...current, webhookUrl: event.target.value }))} placeholder="https://mi-erp.com/api/asistencia" />
              </div>

              <div className="field">
                <label>Headers HTTP</label>
                <textarea className="textarea" value={erpForm.headers} onChange={(event) => setErpForm((current) => ({ ...current, headers: event.target.value }))} />
              </div>

              <div className="field">
                <label>Mapeo de campos</label>
                <textarea className="textarea" value={erpForm.fieldMap} onChange={(event) => setErpForm((current) => ({ ...current, fieldMap: event.target.value }))} />
              </div>

              <div className="badge info">{erpHint}</div>

              <label className="chip" style={{ justifyContent: 'flex-start' }}>
                <input type="checkbox" checked={erpForm.envioAuto} onChange={(event) => setErpForm((current) => ({ ...current, envioAuto: event.target.checked }))} />
                <span>Enviar automáticamente en cada marcaje</span>
              </label>
              {formError ? <div className="badge danger">{formError}</div> : null}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" type="button" onClick={handleSaveErp}>Guardar</button>
            </div>
          </div>
        </div>
      )}

      {huellaModalOpen && (
        <div className="overlay" onClick={closeHuellaModal} role="presentation">
          <div className="modal" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()} role="presentation">
            <div className="modal-head">
              <h3 className="modal-title">Registrar huella</h3>
              <p className="modal-subtitle">Persona: {huellaPersonaNombre}</p>
            </div>
            <div className="modal-body">
              {!registrandoHuella && huellaMensaje === '' ? (
                <>
                  <p style={{ marginBottom: 12 }}>Selecciona el dispositivo para registrar la huella:</p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 200, overflowY: 'auto' }}>
                    {devices.filter((d) => d.online).map((d) => (
                      <label
                        key={d.id}
                        className="chip"
                        style={{ justifyContent: 'flex-start', cursor: 'pointer', padding: '10px 14px' }}
                      >
                        <input
                          type="radio"
                          name="huellaDevice"
                          checked={huellaDeviceId === d.id}
                          onChange={() => setHuellaDeviceId(d.id)}
                        />
                        <span style={{ marginLeft: 8 }}>
                          <strong>{d.nombre}</strong>
                          <span className="muted" style={{ marginLeft: 8 }}>({d.ip})</span>
                        </span>
                      </label>
                    ))}
                    {devices.filter((d) => d.online).length === 0 && (
                      <p className="muted">No hay dispositivos en línea disponibles.</p>
                    )}
                  </div>
                </>
              ) : (
                <div style={{ textAlign: 'center', padding: '20px 0' }}>
                  {registrandoHuella ? (
                    <>
                      <span className="status-dot live" style={{ margin: '0 auto 12px' }} />
                      <p>{huellaMensaje}</p>
                    </>
                  ) : (
                    <p className={`badge ${huellaMensaje.includes('Error') ? 'danger' : 'info'}`}>{huellaMensaje}</p>
                  )}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeHuellaModal} disabled={registrandoHuella}>
                Cancelar
              </button>
              {!registrandoHuella && huellaMensaje === '' && (
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={handleRegistrarHuella}
                  disabled={!huellaDeviceId}
                >
                  Registrar huella
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {webcamActive && (
        <div className="overlay" onClick={handleWebcamCancel} role="presentation">
          <div className="modal" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()} role="presentation">
            <div className="modal-head">
              <h3 className="modal-title">Capturar rostro</h3>
              <p className="modal-subtitle">{capturedImage ? 'Confirma o vuelve a capturar.' : 'Centra tu rostro frente a la cámara y presiona Capturar.'}</p>
            </div>
            <div className="modal-body" style={{ textAlign: 'center' }}>
              {!capturedImage ? (
                <div style={{ position: 'relative', background: '#000', borderRadius: 8, overflow: 'hidden' }}>
                  <video
                    id="webcam-video"
                    autoPlay
                    playsInline
                    muted
                    style={{ width: '100%', display: 'block' }}
                    ref={(el) => {
                      if (el && captureStream) {
                        el.srcObject = captureStream;
                        el.play().catch(() => {});
                      }
                    }}
                  />
                </div>
              ) : (
                <div style={{ position: 'relative', background: '#000', borderRadius: 8, overflow: 'hidden' }}>
                  <img src={capturedImage} alt="Captura" style={{ width: '100%', display: 'block' }} />
                </div>
              )}
              {uploadingRostro && (
                <div style={{ marginTop: 12, color: '#6b7280' }}>Procesando rostro...</div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={handleWebcamCancel} disabled={uploadingRostro}>
                Cancelar
              </button>
              {!capturedImage ? (
                <button className="btn btn-primary" type="button" onClick={handleWebcamCapture}>
                  Capturar
                </button>
              ) : (
                <>
                  <button className="btn btn-secondary" type="button" onClick={handleWebcamRetake} disabled={uploadingRostro}>
                    Volver a capturar
                  </button>
                  <button className="btn btn-primary" type="button" onClick={handleWebcamConfirm} disabled={uploadingRostro}>
                    Confirmar
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {toast ? (
        <div className={`floating-toast ${toast.kind}`} role="status" aria-live="polite">
          <span className="status-dot live" />
          <span>{toast.message}</span>
        </div>
      ) : null}
    </div>
  );
}