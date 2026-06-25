'use client';

import { useState } from 'react';
import { consultarSolicitudEliminacion } from '@/lib/auth-api';
import Link from 'next/link';

type EstadoSolicitud = 'pendiente' | 'aprobada' | 'rechazada';

interface ConsultaResult {
  estado: EstadoSolicitud;
  fecha_solicitud: string | null;
  fecha_resolucion: string | null;
}

const estadoConfig: Record<EstadoSolicitud, { label: string; color: string; bg: string; icon: string }> = {
  pendiente: { label: 'Pendiente', color: '#d97706', bg: '#fffbeb', icon: '⏳' },
  aprobada: { label: 'Aprobada', color: '#16a34a', bg: '#f0fdf4', icon: '✓' },
  rechazada: { label: 'Rechazada', color: '#dc2626', bg: '#fef2f2', icon: '✗' },
};

export default function SeguimientoEliminacionPage() {
  const [codigo, setCodigo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resultado, setResultado] = useState<ConsultaResult | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    setResultado(null);
    setLoading(true);
    try {
      const res = await consultarSolicitudEliminacion(codigo.trim());
      setResultado({ estado: res.estado as EstadoSolicitud, fecha_solicitud: res.fecha_solicitud, fecha_resolucion: res.fecha_resolucion });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al consultar la solicitud');
    } finally {
      setLoading(false);
    }
  }

  function formatDate(value: string | null) {
    if (!value) return '—';
    return new Date(value).toLocaleString('es-CL');
  }

  const cfg = resultado ? estadoConfig[resultado.estado] : null;

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', padding: 24, background: '#f1f5f9' }}>
      <div style={{ maxWidth: 480, width: '100%' }}>
        <div style={{ background: '#fff', borderRadius: 16, padding: 40, boxShadow: '0 4px 24px rgba(0,0,0,0.06)' }}>
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 8px' }}>Consultar estado</h1>
            <p style={{ color: '#64748b', margin: 0, fontSize: 15 }}>Ingresa tu código de seguimiento para conocer el estado de tu solicitud.</p>
          </div>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 6, color: '#1e293b' }}>Código de seguimiento</label>
              <input
                type="text"
                value={codigo}
                onChange={(event) => setCodigo(event.target.value)}
                placeholder="Ej: 550e8400-e29b-..."
                required
                style={{ width: '100%', padding: '10px 14px', border: '1px solid #e2e8f0', borderRadius: 10, fontSize: 15, outline: 'none', boxSizing: 'border-box', fontFamily: 'monospace' }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{ width: '100%', padding: '12px 24px', background: loading ? '#94a3b8' : '#1d4ed8', color: '#fff', border: 'none', borderRadius: 10, fontSize: 16, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer' }}
            >
              {loading ? 'Consultando...' : 'Consultar estado'}
            </button>
          </form>

          {error && (
            <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', marginTop: 20, color: '#dc2626', fontSize: 14 }}>{error}</div>
          )}

          {resultado && cfg && (
            <div style={{ marginTop: 28 }}>
              <div style={{ background: cfg.bg, borderRadius: 12, padding: 24, textAlign: 'center' }}>
                <div style={{ fontSize: 40, marginBottom: 8 }}>{cfg.icon}</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: cfg.color, marginBottom: 4 }}>{cfg.label}</div>
                <div style={{ fontSize: 13, color: '#64748b', marginTop: 16 }}>
                  <p style={{ margin: '4px 0' }}>Solicitado: {formatDate(resultado.fecha_solicitud)}</p>
                  {resultado.fecha_resolucion && <p style={{ margin: '4px 0' }}>Resuelto: {formatDate(resultado.fecha_resolucion)}</p>}
                </div>
              </div>
            </div>
          )}
        </div>

        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <Link href="/solicitar-eliminacion" style={{ color: '#1d4ed8', fontSize: 14, textDecoration: 'none' }}>Solicitar eliminación de datos</Link>
          <span style={{ color: '#e2e8f0', margin: '0 12px' }}>|</span>
          <Link href="/login" style={{ color: '#64748b', fontSize: 14, textDecoration: 'none' }}>Iniciar sesión</Link>
        </div>
      </div>
    </div>
  );
}
