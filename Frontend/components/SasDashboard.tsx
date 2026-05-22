'use client';

import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
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

type Section = 'dashboard' | 'asistencias' | 'personas' | 'turnos' | 'asignaciones' | 'dispositivos' | 'erp' | 'logs';
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
  logs: '/logs'
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
  const [modal, setModal] = useState<'persona' | 'turno' | 'asignacion' | 'erp' | null>(null);
  const [filterDate, setFilterDate] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterMethod, setFilterMethod] = useState('');
  const [logFilter, setLogFilter] = useState<'all' | 'ok' | 'err' | 'info' | 'warn'>('all');
  const [days, setDays] = useState<string[]>(['L', 'M', 'X', 'J', 'V']);
  const [formError, setFormError] = useState('');

  const [personaForm, setPersonaForm] = useState({ nombre: '', rut: '', email: '' });
  const [turnoForm, setTurnoForm] = useState({ nombre: '', inicio: '08:00', fin: '17:00' });
  const [asignacionForm, setAsignacionForm] = useState({ personaId: '', turnoId: '' });
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

      const [personasRes, turnosRes, asignacionesRes, asistenciasRes, devicesRes, erpRes, logsRes] = await Promise.all([
        needsPersonas ? getPersonas() : Promise.resolve(null),
        needsTurnos ? getTurnos() : Promise.resolve(null),
        needsAsignaciones ? getAsignaciones() : Promise.resolve(null),
        needsAsistencias ? getAsistencias() : Promise.resolve(null),
        needsDevices ? getDispositivos() : Promise.resolve(null),
        needsErp ? getErp() : Promise.resolve(null),
        needsLogs ? getLogs() : Promise.resolve(null)
      ]);

      if (!alive) return;

      if (personasRes) setPersonas(personasRes);
      if (turnosRes) setTurnos(turnosRes);
      if (asignacionesRes) setAsignaciones(asignacionesRes);
      if (asistenciasRes) setAsistencias(asistenciasRes);
      if (devicesRes) {
        setDevices(devicesRes.map((item) => ({
          nombre: item.nombre,
          ip: item.ip_local || '—',
          online: (item.estado || '').toLowerCase() === 'activo',
          marcajes: 0,
          mem: 0,
          camara: false,
          estado: item.estado
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
          activo: item.activo
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
          activo: item.activo
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
      showToast('success', `Persona ${nombre} registrada`);
      const registerUrl = `${deviceBase}/register?name=${encodeURIComponent(nombre)}&rut=${encodeURIComponent(rut)}&email=${encodeURIComponent(personaForm.email.trim())}`;
      window.open(registerUrl, '_blank', 'noopener,noreferrer');
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
    if (!asignacionForm.personaId || !asignacionForm.turnoId) {
      setFormError('Selecciona una persona y un turno');
      return;
    }

    const result = await createAsignacion({ persona_id: asignacionForm.personaId, turno_id: asignacionForm.turnoId });

    if (result && 'ok' in result && result.ok) {
      pushLog('ok', `Asignación creada para persona ${asignacionForm.personaId}`);
      showToast('success', 'Asignación creada');
      closeModal();
      setAsignacionForm({ personaId: '', turnoId: '' });
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
      pushLog('ok', `Persona eliminada: ${personaId}`);
      showToast('success', 'Persona eliminada');
      return;
    }

    showToast('error', 'No se pudo eliminar la persona');
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

  function handleMarkHuella(personaId: string) {
    const nextHuella = Math.max(1, ...personas.map((item) => item.huella_id || 0)) + 1;
    setPersonaHuella(personaId, nextHuella).then((result) => {
      if (result && 'ok' in result && result.ok) {
        setPersonas((current) => current.map((item) => (item.id === personaId ? { ...item, huella_id: nextHuella } : item)));
        pushLog('ok', `Huella asignada a persona ${personaId}`);
        showToast('success', 'Huella actualizada');
        return;
      }

      showToast('error', 'No se pudo actualizar la huella');
    });
  }

  function handleQuickEntry() {
    showToast('error', 'El marcaje manual quedó deshabilitado para usar solo datos de la base de datos');
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
    logs: 'Actividad y trazabilidad'
  }[section];

  const currentSubtitle = {
    dashboard: 'Una vista centralizada con métricas, estados y acciones rápidas para operación diaria.',
    asistencias: 'Filtra entradas, salidas y estado de sincronización con exportación CSV.',
    personas: 'Gestiona la base de personas y asigna huellas sin salir del panel.',
    turnos: 'Define jornadas, horarios y días activos desde una interfaz más clara.',
    asignaciones: 'Relaciona personas y turnos con control visual del estado vigente.',
    dispositivos: 'Supervisa nodos ESP32, cámara, RAM libre y acceso al panel local.',
    erp: 'Guarda endpoints, cabeceras y mapeos sin tocar el backend.',
    logs: 'Revisa eventos, filtrado de mensajes y evidencia operativa.'
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

        <div className="nav-group">
          <div className="nav-label">Sistema</div>
          <SectionButton active={section === 'dispositivos'} href={sectionPaths.dispositivos} onClick={() => setSidebarOpen(false)}>
            <span>Dispositivos</span>
          </SectionButton>
          <SectionButton active={section === 'erp'} href={sectionPaths.erp} onClick={() => setSidebarOpen(false)}>
            <span>ERP</span>
          </SectionButton>
          <SectionButton active={section === 'logs'} href={sectionPaths.logs} onClick={() => setSidebarOpen(false)}>
            <span>Logs</span>
          </SectionButton>
        </div>

        <div className="sidebar-card">
          <div className="status-row">
            <div className="status-dot live" />
            <div>
              <div className="sidebar-card-title">Backend conectado</div>
              <div className="sidebar-card-subtitle">{apiBaseUrl()}</div>
            </div>
          </div>
          <div className="sidebar-card-subtitle" style={{ marginTop: 12 }}>
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
            <span className="chip"><strong>{stats.onlineDevices}</strong> dispositivos online</span>
            <button className="btn btn-secondary" type="button" onClick={handleSyncAll}>
              Sincronizar
            </button>
            <button className="btn btn-primary" type="button" onClick={() => openModal(section === 'personas' ? 'persona' : section === 'turnos' ? 'turno' : section === 'asignaciones' ? 'asignacion' : 'erp')}>
              Acción rápida
            </button>
          </div>
        </header>

        <section className="hero">
          <div className="panel hero-main">
            <div className="split-row" style={{ alignItems: 'start' }}>
              <div style={{ maxWidth: 720 }}>
                <span className="eyebrow">Operación en tiempo real</span>
                <h2 className="page-title" style={{ fontSize: 'clamp(1.7rem, 3vw, 3.1rem)', marginTop: 12 }}>
                  Un panel más completo para control de asistencia, biometría y dispositivos IoT.
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
                            <button className="btn btn-secondary" type="button" onClick={() => handleMarkHuella(item.id)}>Huella</button>
                            <button className="btn btn-danger" type="button" onClick={() => handleDeletePersona(item.id)}>Eliminar</button>
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
                            {item.dias.split('').map((code) => (
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
            </div>

            <div className="device-grid">
              {dashboardDevices.map((item) => (
                <article className="device-card" key={item.ip}>
                  <div className="device-head">
                    <div>
                      <div className="device-name">{item.nombre}</div>
                      <div className="device-ip">{item.ip}</div>
                    </div>
                    <Badge tone={item.online ? 'success' : 'warning'}>{item.online ? 'online' : 'offline'}</Badge>
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
                    <a className="btn btn-secondary" href={deviceBase} target="_blank" rel="noreferrer">Abrir panel</a>
                    <a className="btn btn-secondary" href={`${deviceBase}/logs`} target="_blank" rel="noreferrer">Logs</a>
                    <button className="btn btn-secondary" type="button" onClick={() => handleDeviceSync(item.ip)}>Sync</button>
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
                  <div className="device-actions" style={{ marginTop: 16 }}>
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
      </main>

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
                <select value={asignacionForm.personaId} onChange={(event) => setAsignacionForm((current) => ({ ...current, personaId: event.target.value }))}>
                  <option value="">Selecciona una persona</option>
                  {personas.map((item) => (
                    <option value={item.id} key={item.id}>
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

      {toast ? (
        <div className={`floating-toast ${toast.kind}`} role="status" aria-live="polite">
          <span className="status-dot live" />
          <span>{toast.message}</span>
        </div>
      ) : null}
    </div>
  );
}