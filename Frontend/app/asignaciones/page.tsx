import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function AsignacionesPage() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="asignaciones" />
    </RequireAuth>
  );
}