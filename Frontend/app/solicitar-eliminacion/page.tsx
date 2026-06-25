'use client';

import { useState } from 'react';
import { solicitarEliminacionDatos } from '@/lib/auth-api';
import Link from 'next/link';

export default function SolicitarEliminacionPage() {
  const [rut, setRut] = useState('');
  const [email, setEmail] = useState('');
  const [motivo, setMotivo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resultado, setResultado] = useState<{ codigo_seguimiento: string; mensaje: string } | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await solicitarEliminacionDatos({ rut: rut.trim(), email: email.trim() || undefined, motivo: motivo.trim() || undefined });
      setResultado(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear la solicitud');
    } finally {
      setLoading(false);
    }
  }

  async function handleCopy() {
    if (!resultado) return;
    try {
      await navigator.clipboard.writeText(resultado.codigo_seguimiento);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch { /* ignore */ }
  }

  if (resultado) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', padding: 24, background: '#f1f5f9' }}>
        <div style={{ maxWidth: 520, width: '100%', background: '#fff', borderRadius: 16, padding: 40, boxShadow: '0 4px 24px rgba(0,0,0,0.06)' }}>
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{ width: 64, height: 64, borderRadius: '50%', background: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', fontSize: 32 }}>✓</div>
            <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 8px' }}>Solicitud creada</h1>
            <p style={{ color: '#64748b', margin: 0, fontSize: 15, lineHeight: 1.5 }}>{resultado.mensaje}</p>
          </div>

          <div style={{ background: '#f8fafc', borderRadius: 12, padding: 20, textAlign: 'center', marginBottom: 24 }}>
            <p style={{ color: '#64748b', fontSize: 13, margin: '0 0 8px' }}>Tu código de seguimiento</p>
            <p style={{ fontFamily: 'monospace', fontSize: 28, fontWeight: 700, letterSpacing: 6, color: '#1d4ed8', margin: '0 0 12px', userSelect: 'all' }}>{resultado.codigo_seguimiento}</p>
            <button type="button" onClick={handleCopy} style={{ background: copied ? '#16a34a' : '#1d4ed8', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 20px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
              {copied ? 'Copiado' : 'Copiar código'}
            </button>
          </div>

          {email && (
            <p style={{ fontSize: 13, color: '#64748b', textAlign: 'center', margin: '0 0 24px' }}>
              También te enviamos el código por correo a <strong>{email}</strong>.
            </p>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Link href="/seguimiento-eliminacion" style={{ display: 'block', textAlign: 'center', padding: '12px 24px', background: '#f1f5f9', borderRadius: 10, color: '#1e293b', fontWeight: 600, fontSize: 15, textDecoration: 'none' }}>
              Consultar estado de mi solicitud
            </Link>
            <Link href="/login" style={{ display: 'block', textAlign: 'center', padding: '12px 24px', color: '#64748b', fontSize: 14, textDecoration: 'none' }}>
              Volver al inicio de sesión
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', padding: 24, background: '#f1f5f9' }}>
      <div style={{ maxWidth: 520, width: '100%' }}>
        <div style={{ background: '#fff', borderRadius: 16, padding: 40, boxShadow: '0 4px 24px rgba(0,0,0,0.06)' }}>
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{ width: 64, height: 64, borderRadius: '50%', background: '#fee2e2', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', fontSize: 28 }}>!</div>
            <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 8px' }}>Solicitar eliminación de datos</h1>
            <p style={{ color: '#64748b', margin: 0, fontSize: 15, lineHeight: 1.5 }}>
              Al enviar esta solicitud, tu RUT, datos faciales y huella dactilar serán eliminados del sistema.<br />
              <strong>Tus registros de asistencia se mantendrán intactos.</strong>
            </p>
          </div>

          {error && (
            <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10, padding: '12px 16px', marginBottom: 20, color: '#dc2626', fontSize: 14 }}>{error}</div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div>
              <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 6, color: '#1e293b' }}>RUT *</label>
              <input
                type="text"
                value={rut}
                onChange={(event) => setRut(event.target.value)}
                placeholder="12.345.678-9"
                required
                style={{ width: '100%', padding: '10px 14px', border: '1px solid #e2e8f0', borderRadius: 10, fontSize: 15, outline: 'none', boxSizing: 'border-box' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 6, color: '#1e293b' }}>Email (opcional)</label>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="correo@ejemplo.cl"
                style={{ width: '100%', padding: '10px 14px', border: '1px solid #e2e8f0', borderRadius: 10, fontSize: 15, outline: 'none', boxSizing: 'border-box' }}
              />
              <p style={{ margin: '6px 0 0', fontSize: 12, color: '#94a3b8' }}>Te enviaremos el código de seguimiento por correo.</p>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 6, color: '#1e293b' }}>Motivo (opcional)</label>
              <textarea
                value={motivo}
                onChange={(event) => setMotivo(event.target.value)}
                placeholder="¿Por qué deseas eliminar tus datos?"
                rows={3}
                style={{ width: '100%', padding: '10px 14px', border: '1px solid #e2e8f0', borderRadius: 10, fontSize: 15, outline: 'none', resize: 'vertical', boxSizing: 'border-box', fontFamily: 'inherit' }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{ width: '100%', padding: '12px 24px', background: loading ? '#94a3b8' : '#dc2626', color: '#fff', border: 'none', borderRadius: 10, fontSize: 16, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer' }}
            >
              {loading ? 'Enviando solicitud...' : 'Solicitar eliminación de datos'}
            </button>
          </form>
        </div>

        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <Link href="/login" style={{ color: '#64748b', fontSize: 14, textDecoration: 'none' }}>Volver al inicio de sesión</Link>
          <span style={{ color: '#e2e8f0', margin: '0 12px' }}>|</span>
          <Link href="/seguimiento-eliminacion" style={{ color: '#1d4ed8', fontSize: 14, textDecoration: 'none' }}>Ya tengo un código de seguimiento</Link>
        </div>
      </div>
    </div>
  );
}
