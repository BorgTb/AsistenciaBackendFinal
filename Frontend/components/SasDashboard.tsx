'use client';

import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
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
  actualizarRostro,
  generarPinEnrolamiento,
  generarPasswordDispositivo,
  eliminarPasswordDispositivo,
  getEmpresas,
  getUsuarios,
  registerUser,
  type Empresa,
  type UsuarioWeb
} from '@/lib/auth-api';
import {
  apiBaseUrl,
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
  getErp,
  getLogs,
  getPersonas,
  getTurnos,
  testErp,
  setPersonaHuella
} from '@/lib/api';
import type { Asignacion, Asistencia, DeviceStatus, ErpIntegration, LogEntry, Persona, Turno } from '@/lib/types';

type Section = 'dashboard' | 'asistencias' | 'personas' | 'turnos' | 'asignaciones' | 'dispositivos' | 'erp' | 'logs' | 'usuarios' | 'empresas';
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
  empresas: '/empresas'
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
  const [empresaForm, setEmpresaForm] = useState({ nombre: '', rut_empresa: '', email_contacto: '', telefono: '', direccion: '' });
  const [passwordForm, setPasswordForm] = useState({ passwordActual: '', passwordNueva: '', confirmacion: '' });
  const [generatedPin, setGeneratedPin] = useState('');
  const [deviceForm, setDeviceForm] = useState({ nombre: '', ip: '' });
  const [deviceVerify, setDeviceVerify] = useState<'idle' | 'checking' | 'ok' | 'fail'>('idle');
  const [deviceVerifyMsg, setDeviceVerifyMsg] = useState('');
  const [editingDeviceId, setEditingDeviceId] = useState<string | null>(null);
  const [editDeviceName, setEditDeviceName] = useState('');
  const [generatedDevicePassword, setGeneratedDevicePassword] = useState<string | null>(null);
  const [generatingPasswordFor, setGeneratingPasswordFor] = useState<string | null>(null);
  const [rostroPersonaId, setRostroPersonaId] = useState<string | null>(null);
  const [uploadingRostro, setUploadingRostro] = useState(false);
  const [webcamActive, setWebcamActive] = useState(false);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [captureStream, setCaptureStream] = useState<MediaStream | null>(null);

  const [personaForm, setPersonaForm] = useState({ nombre: '', rut: '', email: '' });
  const [turnoForm, setTurnoForm] = useState({ nombre: '', inicio: '08:00', fin: '17:00' });
  const [asignacionForm, setAsignacionForm] = useState({ rut: '', turnoId: '' });
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

  useEffect(() => {
    let alive = true;

    async function loadData(view: Section) {
      const needsPersonas = view === 'dashboard' || view === 'personas' || view === 'asignaciones';
      const needsTurnos = view === 'dashboard' || view === 'turnos' || view === 'asignaciones';
      const needsAsignaciones = view === 'dashboard' || view === 'asignaciones';
      const needsAsistencias = view === 'dashboard' || view === 'asistencias';
      const needsDevices = view === 'dashboard' || view === 'dispositivos';
      const needsErp = view === 'erp';
      const needsLogs = view === 'logs';
      const needsUsuarios = view === 'usuarios';
      const needsEmpresas = view === 'empresas' || (view === 'usuarios' && user?.rol === 'admin');

      const [personasRes, turnosRes, asignacionesRes, asistenciasRes, devicesRes, erpRes, logsRes, usuariosRes, empresasRes] = await Promise.all([
        needsPersonas ? getPersonas() : Promise.resolve(null),
        needsTurnos ? getTurnos() : Promise.resolve(null),
        needsAsignaciones ? getAsignaciones() : Promise.resolve(null),
        needsAsistencias ? getAsistencias() : Promise.resolve(null),
        needsDevices ? getDispositivos() : Promise.resolve(null),
        needsErp ? getErp() : Promise.resolve(null),
        needsLogs ? getLogs() : Promise.resolve(null),
        needsUsuarios ? getUsuarios() : Promise.resolve(null),
        needsEmpresas ? getEmpresas() : Promise.resolve(null)
      ]);

      if (!alive) return;

      if (personasRes) setPersonas(personasRes);
      if (turnosRes) setTurnos(turnosRes);
      if (asignacionesRes) setAsignaciones(asignacionesRes);
      if (asistenciasRes) setAsistencias(asistenciasRes);
      if (devicesRes) {
        setDevices(devicesRes.map((item) => ({
          id: item.id,
          nombre: item.nombre,
          ip: item.ip_local || '—',
          online: (item.estado || '').toLowerCase() === 'activo',
          marcajes: 0,
          mem: 0,
          camara: false,
          estado: item.estado,
          tienePassword: (item as Record<string, unknown>).tiene_password as boolean,
          passwordPendiente: (item as Record<string, unknown>).password_pendiente as boolean
        })));
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

  function openModal(nextModal: NonNullable<typeof modal>) {
    setFormError('');
    setModal(nextModal);
  }

  function closeModal() {
    setModal(null);
    setFormError('');
    setDeviceForm({ nombre: '', ip: '' });
    setDeviceVerify('idle');
    setDeviceVerifyMsg('');
    setEditingUsuario(null);
    setRegisterForm({ nombre: '', email: '', password: '', rol: 'trabajador', empresa_id: undefined });
  }

  async function refreshData() {
    pushLog('info', 'Refrescando datos desde el backend');
    await Promise.all([
      refreshSection(section),
      section === 'dashboard' ? Promise.all([refreshSection('personas'), refreshSection('turnos')]) : Promise.resolve()
    ]);
    showToast('success', 'Datos actualizados');
    pushLog('ok', 'Sincronización visual completada');
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
        setDevices(devicesRes.map((item) => ({
          id: item.id,
          nombre: item.nombre,
          ip: item.ip_local || '—',
          online: (item.estado || '').toLowerCase() === 'activo',
          marcajes: 0,
          mem: 0,
          camara: false,
          estado: item.estado
        })));
      }
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

    const result = await createPersona({ nombre, rut, email: personaForm.email.trim() });

    if (result && 'ok' in result && result.ok) {
      pushLog('ok', `Persona creada: ${nombre}`);
      showToast('success', `Persona ${nombre} guardada. Complete huella/rostro desde el dispositivo ESP32.`);
      closeModal();
      setPersonaForm({ nombre: '', rut: '', email: '' });
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
    const result = await createTurno({ nombre, inicio: turnoForm.inicio, fin: turnoForm.fin, dias });

    if (result && 'ok' in result && result.ok) {
      pushLog('ok', `Turno creado: ${nombre}`);
      showToast('success', `Turno ${nombre} creado`);
      closeModal();
      setTurnoForm({ nombre: '', inicio: '08:00', fin: '17:00' });
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
      pushLog('ok', `ERP probado: ${nombre}`);
      showToast('success', `Test ejecutado para ${nombre}`);
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

  function handleSyncAll() {
    refreshData();
    showToast('success', 'Sincronización iniciada');
  }

  function handleDeviceSync(ip: string) {
    pushLog('info', `Sincronización solicitada: ${ip}`);
    showToast('success', `El dispositivo ${ip} se gestiona desde su backend`);
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
    const base64 = capturedImage.split(',')[1];
    const result = await registrarRostro(rostroPersonaId, base64);
    if (result && 'ok' in result && result.ok) {
      pushLog('ok', `Rostro registrado para RUT ${rostroPersonaId}`);
      showToast('success', 'Rostro registrado correctamente');
    } else {
      const msg = result && 'error' in result ? String(result.error) : 'No se pudo registrar el rostro';
      showToast('error', msg);
    }
    setUploadingRostro(false);
    handleWebcamCancel();
  }

  function handleQuickEntry() {
    showToast('error', 'El marcaje manual quedó deshabilitado para usar solo datos de la base de datos');
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
    setDeviceVerify('checking');
    setDeviceVerifyMsg('');
    const result = await verificarDispositivo(ip);
    if (result && 'ok' in result && result.ok) {
      setDeviceVerify('ok');
      setDeviceVerifyMsg(`Dispositivo responde · MAC: ${result.datos?.mac || 'N/D'}`);
      showToast('success', 'Dispositivo verificado');
    } else {
      setDeviceVerify('fail');
      const mensaje = result && 'error' in result ? String(result.error) : 'No responde';
      setDeviceVerifyMsg(mensaje);
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

    const result = await createEmpresa({
      nombre: nombre.trim(),
      rut_empresa: empresaForm.rut_empresa.trim(),
      email_contacto: empresaForm.email_contacto.trim(),
      telefono: empresaForm.telefono.trim(),
      direccion: empresaForm.direccion.trim()
    });

    if (result && 'ok' in result && result.ok) {
      showToast('success', 'Empresa creada');
      setEmpresaForm({ nombre: '', rut_empresa: '', email_contacto: '', telefono: '', direccion: '' });
      closeModal();
      await refreshData();
      return;
    }

    showToast('error', result && 'error' in result ? String(result.error) : 'Error al crear empresa');
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
    if (user?.rol === 'admin' && rol) payload.rol = rol;

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
    dashboard: 'Dashboard ejecutivo',
    asistencias: 'Asistencias y marcajes',
    personas: 'Personas y biometría',
    turnos: 'Turnos y calendario',
    asignaciones: 'Asignaciones activas',
    dispositivos: 'Dispositivos conectados',
    erp: 'Integraciones ERP',
    logs: 'Actividad y trazabilidad',
    usuarios: 'Gestión de usuarios',
    empresas: 'Gestión de empresas'
  }[section];

  const currentSubtitle = {
    dashboard: 'Una vista centralizada con métricas, estados y acciones rápidas para operación diaria.',
    asistencias: 'Filtra entradas, salidas y estado de sincronización con exportación CSV.',
    personas: 'Gestiona la base de personas y asigna huellas sin salir del panel.',
    turnos: 'Define jornadas, horarios y días activos desde una interfaz más clara.',
    asignaciones: 'Relaciona personas y turnos con control visual del estado vigente.',
    dispositivos: 'Supervisa nodos ESP32, cámara, RAM libre y acceso al panel local.',
    erp: 'Guarda endpoints, cabeceras y mapeos sin tocar el backend.',
    logs: 'Revisa eventos, filtrado de mensajes y evidencia operativa.',
    usuarios: 'Administra usuarios del sistema, roles y permisos de acceso.',
    empresas: 'Crea y administra empresas del sistema. Cada empresa tiene sus propios usuarios, dispositivos y datos.'
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
            <div className="brand-subtitle">Next.js + Flask + IoT</div>
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

        <div className="sidebar-card">
          <div className="status-row">
            <div className="status-dot live" />
            <div>
              <div className="sidebar-card-title">Backend conectado</div>
              <div className="sidebar-card-subtitle">{apiBaseUrl()}</div>
            </div>
          </div>
          {user && (
            <div className="sidebar-card-subtitle" style={{ marginTop: 12 }}>
              {user.empresa_nombre} · {user.rol}
            </div>
          )}
          <div className="sidebar-card-subtitle" style={{ marginTop: user ? 2 : 12 }}>
            El frontend consume Flask por REST y todo el contenido operativo proviene de la base de datos.
          </div>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div className="title-block">
            <button className="btn btn-secondary mobile-menu-btn" type="button" onClick={() => setSidebarOpen(true)}>
              Menú
            </button>
            <span className="eyebrow">SAS control center</span>
            <h1 className="page-title">{currentTitle}</h1>
            <p className="page-subtitle">{currentSubtitle}</p>
          </div>

          <div className="top-actions">
            {(user?.rol === 'admin' || user?.rol === 'empleador') && (
              <span className="chip"><strong>{stats.onlineDevices}</strong> dispositivos online</span>
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
                <span className="eyebrow">{user?.rol === 'trabajador' ? 'Mi asistencia' : 'Operación en tiempo real'}</span>
                <h2 className="page-title" style={{ fontSize: 'clamp(1.7rem, 3vw, 3.1rem)', marginTop: 12 }}>
                  {user?.rol === 'trabajador'
                    ? 'Registro de asistencias y turno asignado.'
                    : 'Un panel más completo para control de asistencia, biometría y dispositivos IoT.'}
                </h2>
                <p className="page-subtitle" style={{ marginTop: 12 }}>
                  Conserva tu backend Python y suma una capa Next.js más clara, responsiva y modular. Esta base ya trae navegación, filtros, formularios, logs y una estructura lista para seguir creciendo.
                </p>
              </div>
              <Badge tone="info">REST Flask</Badge>
            </div>

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
                    <span key={index} style={{ height: `${height}%`, background: index >= 5 ? 'linear-gradient(180deg, var(--accent), #89f0b6)' : 'linear-gradient(180deg, var(--accent), rgba(125, 211, 252, 0.28))' }} />
                  ))}
                </div>
              </article>
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">Personas</span>
                  <Badge tone="success">biometría activa</Badge>
                </div>
                <div className="metric-value">{personas.length}</div>
                <div className="metric-foot">{personas.filter((item) => item.huella_id > 0).length} con huella registrada</div>
                <div className="sparkline" aria-hidden>
                  {[30, 24, 48, 44, 58, 60, 74, 82].map((height, index) => (
                    <span key={index} style={{ height: `${height}%`, background: 'linear-gradient(180deg, #89f0b6, rgba(56, 217, 255, 0.4))' }} />
                  ))}
                </div>
              </article>
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">Dispositivos</span>
                  <Badge tone={stats.onlineDevices > 0 ? 'success' : 'warning'}>{stats.onlineDevices} online</Badge>
                </div>
                <div className="metric-value">{devices.length}</div>
                <div className="metric-foot">Cámara, RAM libre y acceso directo al nodo local</div>
                <div className="sparkline" aria-hidden>
                  {[68, 62, 58, 71, 64, 78, 85, 72].map((height, index) => (
                    <span key={index} style={{ height: `${height}%` }} />
                  ))}
                </div>
              </article>
              <article className="metric-card">
                <div className="metric-top">
                  <span className="metric-label">Facial + huella</span>
                  <Badge tone="warning">capturas</Badge>
                </div>
                <div className="metric-value">{stats.facialChecks}</div>
                <div className="metric-foot">Marcajes con combinación biométrica y validación visual</div>
                <div className="sparkline" aria-hidden>
                  {[16, 28, 18, 46, 38, 52, 48, 66].map((height, index) => (
                    <span key={index} style={{ height: `${height}%`, background: 'linear-gradient(180deg, var(--accent-warm), rgba(56, 217, 255, 0.42))' }} />
                  ))}
                </div>
              </article>
            </div>
          </div>

          <div className="side-stack">
            <div className="panel status-panel">
              <div className="split-row">
                <div>
                  <h3 className="section-title">Estado operativo</h3>
                  <p className="section-subtitle">Resumen rápido del ecosistema</p>
                </div>
                <Badge tone="success">estable</Badge>
              </div>

              <div className="status-list">
                <div className="status-item">
                  <div className="status-item-left">
                    <span className="dot-online" />
                    <div>
                      <div className="status-name">Backend Flask</div>
                      <div className="status-meta">{apiBaseUrl()}</div>
                    </div>
                  </div>
                  <Badge tone="success">ok</Badge>
                </div>
                <div className="status-item">
                  <div className="status-item-left">
                    <span className="dot-warning" />
                    <div>
                      <div className="status-name">Dispositivo principal</div>
                      <div className="status-meta">ESP32-CAM / detección facial</div>
                    </div>
                  </div>
                  <Badge tone="warning">live</Badge>
                </div>
                <div className="status-item">
                  <div className="status-item-left">
                    <span className="dot-offline" />
                    <div>
                      <div className="status-name">ERP en DB</div>
                      <div className="status-meta">Integraciones persistidas en PostgreSQL</div>
                    </div>
                  </div>
                  <Badge tone="info">next</Badge>
                </div>
              </div>
            </div>

            <div className="panel quick-panel">
              <div className="split-row">
                <div>
                  <h3 className="section-title">Acciones rápidas</h3>
                  <p className="section-subtitle">Tareas frecuentes del panel</p>
                </div>
              </div>
              <div className="toolbar" style={{ marginTop: 14 }}>
                <button className="btn btn-secondary" type="button" onClick={() => openModal('persona')}>Nueva persona</button>
                <button className="btn btn-secondary" type="button" onClick={() => openModal('turno')}>Nuevo turno</button>
                <button className="btn btn-secondary" type="button" onClick={() => openModal('asignacion')}>Asignar turno</button>
                <button className="btn btn-secondary" type="button" onClick={handleQuickEntry}>Marcaje manual</button>
              </div>
            </div>
          </div>
        </section>

        {(section === 'dashboard' || section === 'asistencias') && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Asistencias recientes</h2>
                <p className="section-subtitle">Puedes filtrar, exportar y revisar estado de sync.</p>
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
                  </select>
                </div>
                <div className="field" style={{ minWidth: 220 }}>
                  <label>Método</label>
                  <select value={filterMethod} onChange={(event) => setFilterMethod(event.target.value)}>
                    <option value="">Todos</option>
                    <option value="huella">Huella</option>
                    <option value="facial+huella">Facial + Huella</option>
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
                            <Badge tone={item.tipo === 'entrada' ? 'success' : 'warning'}>{item.tipo}</Badge>
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
                <p className="section-subtitle">Registro, huella y acciones de mantenimiento.</p>
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
                          <Badge tone={item.huella_id ? 'success' : 'danger'}>{item.huella_id ? `ID ${item.huella_id}` : 'sin huella'}</Badge>
                        </td>
                        <td className="mono muted">{formatDate(item.fecha_registro)}</td>
                        <td>
                          <div className="toolbar">
                            <button className="btn btn-secondary" type="button" disabled={uploadingRostro} onClick={() => handleRostroUpload(item.id)}>{uploadingRostro ? 'Subiendo...' : 'Rostro'}</button>
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
                <p className="section-subtitle">Horario, duración y días activos.</p>
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
                <p className="section-subtitle">Relación vigente entre personas y turnos.</p>
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
                <p className="section-subtitle">Estado del nodo local y acceso rápido al panel de cada equipo.</p>
              </div>
              {(user?.rol === 'admin' || user?.rol === 'empleador') && (
                <button className="btn btn-primary" type="button" onClick={() => openModal('dispositivo')}>
                  Agregar dispositivo
                </button>
              )}
            </div>

            {generatedPin && (
              <div className="card" style={{ marginBottom: 18, borderColor: 'rgba(56,217,255,0.4)', background: 'rgba(56,217,255,0.08)', padding: 20 }}>
                <div className="status-row">
                  <div className="status-dot" style={{ boxShadow: '0 0 0 6px rgba(56,217,255,0.3)' }} />
                  <div>
                    <div className="device-name" style={{ fontWeight: 700, fontSize: '1.1rem' }}>PIN de enrolamiento generado</div>
                    <div className="device-ip">Copia este código para configurar el dispositivo físico</div>
                  </div>
                </div>
                <div className="mono" style={{ marginTop: 16, padding: 16, borderRadius: 12, background: '#000', fontSize: '1.8rem', textAlign: 'center', letterSpacing: '0.3em', fontWeight: 700, color: 'var(--accent)' }}>
                  {generatedPin}
                </div>
                <div className="muted" style={{ marginTop: 12, fontSize: '0.82rem' }}>
                  1. Enciende el dispositivo · 2. Conéctate a su WiFi (192.168.4.1) · 3. Ve a WiFi Setup · 4. Ingresa el PIN y la URL del backend
                </div>
              </div>
            )}

            <div className="device-grid">
              {dashboardDevices.map((item) => (
                <article className="device-card" key={item.ip}>
                  <div className="device-head">
                    <div style={{ flex: 1 }}>
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
                          <div className="device-name">{item.nombre}</div>
                          <div className="device-ip">{item.ip}</div>
                        </>
                      )}
                    </div>
                    <Badge tone={item.online ? 'success' : 'warning'}>{item.online ? 'online' : 'offline'}</Badge>
                    {item.tienePassword ? (
                      <span title={item.passwordPendiente ? 'Contraseña pendiente de aplicar en el dispositivo' : 'Con contraseña'} style={{ fontSize: '1.1rem', marginLeft: 4 }}>
                        {item.passwordPendiente ? '🔑' : '🔒'}
                      </span>
                    ) : (
                      <span title="Sin contraseña" style={{ fontSize: '1.1rem', marginLeft: 4, opacity: 0.5 }}>🔓</span>
                    )}
                  </div>

                  <div className="device-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', marginTop: 16 }}>
                    <div className="card">
                      <div className="muted">Marcajes hoy</div>
                      <div className="metric-value" style={{ fontSize: '1.6rem', marginTop: 8 }}>{item.marcajes}</div>
                    </div>
                    <div className="card">
                      <div className="muted">RAM libre</div>
                      <div className="metric-value" style={{ fontSize: '1.6rem', marginTop: 8, color: item.mem > 70 ? 'var(--warning)' : 'var(--success)' }}>{item.mem}%</div>
                    </div>
                  </div>

                  <div className="progress"><span style={{ width: `${item.mem}%`, background: item.mem > 70 ? 'linear-gradient(90deg, var(--danger), var(--warning))' : 'linear-gradient(90deg, var(--accent), var(--success))' }} /></div>

                  <div className="device-actions">
                    <button className="btn btn-secondary" type="button" onClick={() => { setEditingDeviceId(item.id); setEditDeviceName(item.nombre); }}>Renombrar</button>
                    <button
                      className="btn btn-primary"
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
                    <a className="btn btn-secondary" href={`${deviceBase}/logs`} target="_blank" rel="noreferrer">Logs</a>
                    <button className="btn btn-secondary" type="button" onClick={() => handleDeviceSync(item.ip)}>Sync</button>
                    <button className="btn btn-danger" type="button" onClick={() => handleDeleteDispositivo(item.id, item.nombre)}>Eliminar</button>
                  </div>
                </article>
              ))}
                  {dashboardDevices.length === 0 ? <div className="empty-state">No hay dispositivos registrados en la base de datos.</div> : null}
            </div>
          </section>
        )}

        {section === 'erp' && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Integraciones ERP</h2>
                <p className="section-subtitle">Configuración persistida en PostgreSQL y expuesta por Flask.</p>
              </div>
              <button className="btn btn-secondary" type="button" onClick={() => openModal('erp')}>Agregar ERP</button>
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
                      Ultimo envio: {item.ultimoEnvio ? new Date(item.ultimoEnvio).toLocaleString() : '—'} · {item.ultimoEstado}
                    </div>
                  )}
                  <div className="device-actions" style={{ marginTop: 16 }}>
                    <button className="btn btn-primary" type="button" onClick={() => handleEnviarErp(item.id, item.nombre)}>Enviar</button>
                    <button className="btn btn-secondary" type="button" onClick={() => handleTestErp(item.id, item.nombre)}>Test</button>
                    <button className="btn btn-danger" type="button" onClick={() => handleDeleteErp(item.id)}>Eliminar</button>
                  </div>
                </article>
              ))}
              {erpList.length === 0 ? <div className="empty-state">No hay integraciones ERP cargadas desde la base de datos.</div> : null}
            </div>
          </section>
        )}

        {section === 'logs' && (
          <section className="panel section">
            <div className="section-head">
              <div>
                <h2 className="section-title">Logs</h2>
                <p className="section-subtitle">Eventos de interfaz, backend y tareas del sistema.</p>
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
                <h3 className="section-title">Actividad reciente</h3>
                <p className="section-subtitle">Lo que se está viendo en el panel ahora mismo.</p>
                <div className="status-list" style={{ marginTop: 16 }}>
                  <div className="status-item">
                    <div>
                      <div className="status-name">Endpoint base</div>
                      <div className="status-meta">{apiBaseUrl()}</div>
                    </div>
                    <Badge tone="info">REST</Badge>
                  </div>
                  <div className="status-item">
                    <div>
                      <div className="status-name">Dispositivo</div>
                      <div className="status-meta">{deviceBase}</div>
                    </div>
                    <Badge tone="warning">IoT</Badge>
                  </div>
                  <div className="status-item">
                    <div>
                      <div className="status-name">ERPs guardados</div>
                      <div className="status-meta">{erpList.length}</div>
                    </div>
                    <Badge tone="success">local</Badge>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {section === 'usuarios' && (
          <section className="section">
            <div className="section-head">
              <div>
                <h3 className="section-title">Usuarios del sistema</h3>
                <p className="section-subtitle">Administra cuentas de acceso con roles y permisos.</p>
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
                            {item.rol}
                          </Badge>
                        </td>
                        <td>{item.activo ? 'Sí' : 'No'}</td>
                        <td className="mono muted">{item.created_at ? formatDate(item.created_at) : '—'}</td>
                        <td>
                          <button className="btn btn-ghost" type="button" onClick={() => handleEditUsuario(item)} style={{ marginRight: 8 }}>
                            Editar
                          </button>
                          {(user?.rol === 'admin' || (user?.rol === 'empleador' && item.rol === 'trabajador')) && item.id !== user?.id && (
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
                <p className="section-subtitle">Cada empresa tiene sus propios dispositivos, trabajadores y datos aislados.</p>
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
              <p className="modal-subtitle">Cada empresa aísla sus datos, usuarios, dispositivos y trabajadores.</p>
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
                  disabled={!user?.rol?.includes('admin') && editingUsuario !== null}
                >
                  {user?.rol === 'admin' && <option value="admin">Administrador</option>}
                  {user?.rol === 'admin' && <option value="empleador">Empleador</option>}
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
              <p className="modal-subtitle">Asigna un nombre y genera el PIN. El dispositivo enviará su IP automáticamente al enrolarse.</p>
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
                <div className="card" style={{ marginTop: 16, borderColor: 'rgba(56,217,255,0.4)', background: 'rgba(56,217,255,0.08)', padding: 16 }}>
                  <div className="status-row">
                    <div className="status-dot" style={{ boxShadow: '0 0 0 6px rgba(56,217,255,0.3)' }} />
                    <div>
                      <div className="device-name" style={{ fontWeight: 700 }}>PIN generado</div>
                      <div className="device-ip">Copia este código para configurar el dispositivo</div>
                    </div>
                  </div>
                  <div className="mono" style={{ marginTop: 12, padding: 12, borderRadius: 10, background: '#000', fontSize: '1.5rem', textAlign: 'center', letterSpacing: '0.3em', fontWeight: 700, color: 'var(--accent)' }}>
                    {generatedPin}
                  </div>
                  <div className="muted" style={{ marginTop: 12, fontSize: '0.82rem' }}>
                    1. Enciende el dispositivo · 2. Conéctate a su WiFi (192.168.4.1) · 3. Ve a WiFi Setup · 4. Ingresa el PIN y la URL del backend · 5. El dispositivo se enrolará automáticamente
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
              <div className="card" style={{ borderColor: 'rgba(255,193,7,0.6)', background: 'rgba(255,193,7,0.1)', padding: 14, marginBottom: 16 }}>
                <strong style={{ color: 'var(--warning)' }}>Guarde esta contraseña. Solo se muestra una vez.</strong>
              </div>
              <div className="mono" style={{ padding: 16, borderRadius: 12, background: '#000', fontSize: '1.6rem', textAlign: 'center', letterSpacing: '0.25em', fontWeight: 700, color: 'var(--accent)' }}>
                {generatedDevicePassword}
              </div>
              <div className="muted" style={{ marginTop: 16, fontSize: '0.82rem' }}>
                1. El dispositivo aplicara la contrasena cuando se conecte al backend (cada 60s).<br />
                2. Si esta offline, ingresela manualmente en WiFi Setup del ESP32.<br />
                3. Use esta contrasena en el parametro admin_password al acceder al dispositivo.
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
                <p className="section-subtitle">Se guarda en el backend y luego abre el registro facial/huella del dispositivo.</p>
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
              {formError ? <div className="badge danger">{formError}</div> : null}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeModal}>Cancelar</button>
              <button className="btn btn-primary" type="button" onClick={handleCreatePersona}>Registrar y capturar huella</button>
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
                <p className="section-subtitle">Guarda el endpoint, headers y mapeo de campos en la base de datos.</p>
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