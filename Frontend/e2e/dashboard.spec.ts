import { test, expect } from '@playwright/test';

test.describe('SAS Dashboard E2E — Chromium', () => {
  test('pantalla de login se renderiza', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('.login-form')).toBeVisible();
    await expect(page.locator('.brand-mark')).toHaveText('SAS');
    await expect(page.locator('#login-email')).toBeVisible();
    await expect(page.locator('#login-password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible();
  });

  test('formulario de login muestra campos correctos', async ({ page }) => {
    await page.goto('/login');
    const emailInput = page.locator('#login-email');
    const passwordInput = page.locator('#login-password');
    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(emailInput).toHaveAttribute('type', 'email');
    await expect(passwordInput).toHaveAttribute('type', 'password');
  });

  test('boton de registro de empresa existe', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByText('Registrar mi empresa')).toBeVisible();
  });

  test('redirige a /login si no hay token', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/login/);
  });

  test('modo registro muestra formulario', async ({ page }) => {
    await page.goto('/login');
    await page.click('button:has-text("Registrar mi empresa")');
    await expect(page.locator('#reg-empresa')).toBeVisible();
    await expect(page.locator('#reg-nombre')).toBeVisible();
    await expect(page.locator('#reg-email')).toBeVisible();
    await expect(page.locator('#reg-password')).toBeVisible();
    await expect(page.locator('#reg-password-confirm')).toBeVisible();
  });

  test('volver al login desde registro', async ({ page }) => {
    await page.goto('/login');
    await page.click('button:has-text("Registrar mi empresa")');
    await page.click('button:has-text("Ya tengo cuenta")');
    await expect(page.locator('#login-email')).toBeVisible();
  });
});
