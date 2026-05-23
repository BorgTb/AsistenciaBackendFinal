import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function DispositivosPage() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="dispositivos" />
    </RequireAuth>
  );
}