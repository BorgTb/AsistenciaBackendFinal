'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import type { EmpresaVinculada } from '@/lib/auth-types';

export function LoginForm() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [empresas, setEmpresas] = useState<EmpresaVinculada[]>([]);
  const [empresaSeleccionada, setEmpresaSeleccionada] = useState<number | null>(null);
  const [userName, setUserName] = useState('');

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError('');

    if (!email.trim() || !password) {
      setError('Completa todos los campos');
      return;
    }

    setSubmitting(true);
    try {
      const result = await login(email, password, empresaSeleccionada ?? undefined);

      if (result.ok) {
        window.location.href = '/';
      } else if ('need_empresa' in result && result.need_empresa) {
        setEmpresas(result.empresas);
        setUserName(result.user_name);
        setEmpresaSeleccionada(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al iniciar sesion');
    } finally {
      setSubmitting(false);
    }
  }

  if (empresas.length > 0) {
    return (
      <form className="login-form" onSubmit={(e) => { e.preventDefault(); if (empresaSeleccionada) handleSubmit(e); }}>
        <div className="login-header">
          <div className="brand-mark login-mark">SAS</div>
          <h2 className="login-title">Seleccionar empresa</h2>
          <p className="login-subtitle">{userName}, estás en {empresas.length} {empresas.length === 1 ? 'empresa' : 'empresas'}. Elige dónde ingresar.</p>
        </div>

        {error && <div className="login-error">{error}</div>}

        <div className="field">
          <label>Empresa</label>
          <select
            value={empresaSeleccionada ?? ''}
            onChange={(e) => {
              setEmpresaSeleccionada(Number(e.target.value));
              setError('');
            }}
            disabled={submitting}
          >
            <option value="">Selecciona una empresa</option>
            {empresas.map((emp) => (
              <option key={emp.empresa_id} value={emp.empresa_id}>
                {emp.empresa_nombre} — {emp.rol}
              </option>
            ))}
          </select>
        </div>

        <button
          className="btn btn-accent btn-full"
          type="submit"
          disabled={submitting || !empresaSeleccionada}
          onClick={(e) => { e.preventDefault(); if (empresaSeleccionada) handleSubmit(e); }}
        >
          {submitting ? 'Ingresando...' : 'Ingresar'}
        </button>

        <button className="btn btn-secondary btn-full" type="button" onClick={() => { setEmpresas([]); setEmpresaSeleccionada(null); }}>
          Volver
        </button>
      </form>
    );
  }

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <div className="login-header">
        <div className="brand-mark login-mark">SAS</div>
        <h2 className="login-title">Iniciar sesion</h2>
        <p className="login-subtitle">Ingresa con tu cuenta de empresa</p>
      </div>

      {error && <div className="login-error">{error}</div>}

      <div className="field">
        <label htmlFor="login-email">Email</label>
        <input
          id="login-email"
          type="email"
          placeholder="tu@empresa.cl"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          disabled={submitting}
        />
      </div>

      <div className="field">
        <label htmlFor="login-password">Contrasena</label>
        <input
          id="login-password"
          type="password"
          placeholder="Tu contrasena"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          disabled={submitting}
        />
      </div>

      <button className="btn btn-accent btn-full" type="submit" disabled={submitting}>
        {submitting ? 'Ingresando...' : 'Ingresar'}
      </button>
    </form>
  );
}
