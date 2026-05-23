import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function AsistenciasPage() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="asistencias" />
    </RequireAuth>
  );
}