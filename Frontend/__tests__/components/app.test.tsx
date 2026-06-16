import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server } from '../handlers';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn()
  })
}));

describe('RequireAuth', () => {
  it('muestra loading inicialmente', async () => {
    const React = await import('react');
    const { AuthProvider } = await import('@/lib/auth-context');

    const { RequireAuth } = await import('@/components/RequireAuth');

    const { container } = render(
      React.createElement(AuthProvider, null,
        React.createElement(RequireAuth, null, React.createElement('div', null, 'Dashboard'))
      )
    );

    expect(container.textContent).toBe('Cargando...');
  });

  it('renderiza children cuando usuario autenticado', async () => {
    const React = await import('react');
    const { AuthProvider, useAuth } = await import('@/lib/auth-context');
    const { renderHook, act } = await import('@testing-library/react');
    const { RequireAuth } = await import('@/components/RequireAuth');

    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(AuthProvider, null, children);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await vi.waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login('admin@empresa.cl', 'admin123');
    });

    const { container } = render(
      React.createElement(RequireAuth, null, React.createElement('div', { 'data-testid': 'content' }, 'Dashboard'))
    );

    expect(container.textContent).toContain('Dashboard');
  });
});

describe('LoginForm', () => {
  it('renderiza formulario de login', async () => {
    const React = await import('react');
    const { AuthProvider } = await import('@/lib/auth-context');
    const { LoginForm } = await import('@/components/LoginForm');

    const { container } = render(
      React.createElement(AuthProvider, null,
        React.createElement(LoginForm)
      )
    );

    expect(container.textContent).toContain('Iniciar sesion');
    expect(container.textContent).toContain('Email');
    expect(container.textContent).toContain('Contrasena');
  });

  it('tiene el modo de registro', async () => {
    const React = await import('react');
    const { AuthProvider } = await import('@/lib/auth-context');
    const { LoginForm } = await import('@/components/LoginForm');

    const { container, getByText } = render(
      React.createElement(AuthProvider, null,
        React.createElement(LoginForm)
      )
    );

    const registerBtn = getByText('Registrar mi empresa');
    expect(registerBtn).toBeDefined();
    expect(container.textContent).toContain('Registrar mi empresa');
  });
});
