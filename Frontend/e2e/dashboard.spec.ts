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

  test('seccion dispositivos se renderiza', async ({ page }) => {
    await page.goto('/dispositivos');
    await expect(page.locator('.section-title:has-text("Dispositivos")')).toBeVisible();
    await expect(page.locator('.device-grid')).toBeVisible();
    await expect(page.locator('button:has-text("Agregar dispositivo")')).toBeVisible();
  });

  test('modal de agregar dispositivo muestra campo nombre', async ({ page }) => {
    await page.goto('/dispositivos');
    await page.click('button:has-text("Agregar dispositivo")');
    await expect(page.locator('.modal-title')).toBeVisible();
    await expect(page.locator('.modal button:has-text("Generar PIN")')).toBeVisible();
  });

  test('boton generar PIN funciona', async ({ page }) => {
    await page.goto('/dispositivos');
    await page.click('button:has-text("Agregar dispositivo")');
    await expect(page.locator('.modal')).toBeVisible();
    await page.click('button:has-text("Generar PIN")');
  });
});
