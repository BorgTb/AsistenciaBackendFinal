'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import type { EmpresaVinculada } from '@/lib/auth-types';
import { registerCompany, saveToken } from '@/lib/auth-api';

export function LoginForm() {
  const { login } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [empresas, setEmpresas] = useState<EmpresaVinculada[]>([]);
  const [empresaSeleccionada, setEmpresaSeleccionada] = useState<number | null>(null);
  const [userName, setUserName] = useState('');

  const [regEmpresaNombre, setRegEmpresaNombre] = useState('');
  const [regAdminNombre, setRegAdminNombre] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regPasswordConfirm, setRegPasswordConfirm] = useState('');

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

  async function handleRegister(event: React.FormEvent) {
    event.preventDefault();
    setError('');

    if (!regEmpresaNombre.trim() || !regAdminNombre.trim() || !regEmail.trim() || !regPassword) {
      setError('Completa todos los campos');
      return;
    }

    if (regPassword.length < 4) {
      setError('La contrasena debe tener al menos 4 caracteres');
      return;
    }

    if (regPassword !== regPasswordConfirm) {
      setError('Las contrasenas no coinciden');
      return;
    }

    setSubmitting(true);
    try {
      const result = await registerCompany({
        empresa_nombre: regEmpresaNombre.trim(),
        admin_nombre: regAdminNombre.trim(),
        admin_email: regEmail.trim().toLowerCase(),
        admin_password: regPassword
      });

      if (result.ok) {
        saveToken(result.token);
        window.location.href = '/';
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al registrar la empresa');
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode(newMode: 'login' | 'register') {
    setMode(newMode);
    setError('');
    setEmail('');
    setPassword('');
    setEmpresas([]);
    setEmpresaSeleccionada(null);
    setRegEmpresaNombre('');
    setRegAdminNombre('');
    setRegEmail('');
    setRegPassword('');
    setRegPasswordConfirm('');
  }

  if (empresas.length > 0) {
    return (
      <form className="login-form" onSubmit={(e) => { e.preventDefault(); if (empresaSeleccionada) handleSubmit(e); }}>
        <div className="login-header">
          <div className="brand-mark login-mark">SAS</div>
          <h2 className="login-title">Seleccionar empresa</h2>
          <p className="login-subtitle">{userName}, estas en {empresas.length} {empresas.length === 1 ? 'empresa' : 'empresas'}. Elige donde ingresar.</p>
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

  if (mode === 'register') {
    return (
      <form className="login-form" onSubmit={handleRegister}>
        <div className="login-header">
          <div className="brand-mark login-mark">SAS</div>
          <h2 className="login-title">Registrar empresa</h2>
          <p className="login-subtitle">Crea tu empresa y comienza a usar el dispositivo</p>
        </div>

        {error && <div className="login-error">{error}</div>}

        <div className="field">
          <label htmlFor="reg-empresa">Nombre de la empresa *</label>
          <input
            id="reg-empresa"
            type="text"
            placeholder="Ej: Constructora XYZ S.A."
            value={regEmpresaNombre}
            onChange={(e) => setRegEmpresaNombre(e.target.value)}
            disabled={submitting}
          />
        </div>

        <div className="field">
          <label htmlFor="reg-nombre">Tu nombre completo *</label>
          <input
            id="reg-nombre"
            type="text"
            placeholder="Ej: Juan Perez"
            value={regAdminNombre}
            onChange={(e) => setRegAdminNombre(e.target.value)}
            autoComplete="name"
            disabled={submitting}
          />
        </div>

        <div className="field">
          <label htmlFor="reg-email">Email *</label>
          <input
            id="reg-email"
            type="email"
            placeholder="admin@miempresa.cl"
            value={regEmail}
            onChange={(e) => setRegEmail(e.target.value)}
            autoComplete="email"
            disabled={submitting}
          />
        </div>

        <div className="field">
          <label htmlFor="reg-password">Contrasena *</label>
          <input
            id="reg-password"
            type="password"
            placeholder="Minimo 4 caracteres"
            value={regPassword}
            onChange={(e) => setRegPassword(e.target.value)}
            autoComplete="new-password"
            disabled={submitting}
          />
        </div>

        <div className="field">
          <label htmlFor="reg-password-confirm">Confirmar contrasena *</label>
          <input
            id="reg-password-confirm"
            type="password"
            placeholder="Repite la contrasena"
            value={regPasswordConfirm}
            onChange={(e) => setRegPasswordConfirm(e.target.value)}
            autoComplete="new-password"
            disabled={submitting}
          />
        </div>

        <button className="btn btn-accent btn-full" type="submit" disabled={submitting}>
          {submitting ? 'Registrando...' : 'Crear empresa y cuenta'}
        </button>

        <button className="btn btn-secondary btn-full" type="button" onClick={() => switchMode('login')}>
          Ya tengo cuenta — Iniciar sesion
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

      <button className="btn btn-secondary btn-full" type="button" onClick={() => switchMode('register')}>
        Registrar mi empresa
      </button>
    </form>
  );
}
