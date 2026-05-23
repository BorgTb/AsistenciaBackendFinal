import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function TurnosPage() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="turnos" />
    </RequireAuth>
  );
}