import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { server } from '../handlers';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('lib/auth-context.tsx', () => {
  it('provides loading=false after mount with no token', async () => {
    const { AuthProvider, useAuth } = await import('@/lib/auth-context');
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(AuthProvider, null, children);

    const React = await import('react');
    const { renderHook } = await import('@testing-library/react');

    const { result } = renderHook(() => useAuth(), { wrapper });
    await vi.waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  it('login sets user', async () => {
    const React = await import('react');
    const { AuthProvider, useAuth } = await import('@/lib/auth-context');
    const { renderHook } = await import('@testing-library/react');

    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(AuthProvider, null, children);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await vi.waitFor(() => expect(result.current.loading).toBe(false));

    let loginResult: any;
    await act(async () => {
      loginResult = await result.current.login('admin@empresa.cl', 'admin123');
    });

    expect(loginResult.ok).toBe(true);
    expect(result.current.user).not.toBeNull();
    expect(result.current.user!.email).toBe('admin@empresa.cl');
  });

  it('logout clears user', async () => {
    const React = await import('react');
    const { AuthProvider, useAuth } = await import('@/lib/auth-context');
    const { renderHook } = await import('@testing-library/react');

    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(AuthProvider, null, children);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await vi.waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login('admin@empresa.cl', 'admin123');
    });

    expect(result.current.user).not.toBeNull();

    await act(async () => {
      result.current.logout();
    });

    expect(result.current.user).toBeNull();
  });
});
