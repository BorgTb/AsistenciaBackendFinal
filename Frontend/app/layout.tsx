import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { DM_Sans, Space_Mono } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';

const dmSans = DM_Sans({
  subsets: ['latin'],
  variable: '--font-sans'
});

const spaceMono = Space_Mono({
  weight: ['400', '700'],
  subsets: ['latin'],
  variable: '--font-mono'
});

export const metadata: Metadata = {
  title: 'SAS - Sistema de Asistencia',
  description: 'Plataforma corporativa de control de asistencia, biometría y dispositivos IoT.'
};

export default function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="es" className={`${dmSans.variable} ${spaceMono.variable}`}>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}