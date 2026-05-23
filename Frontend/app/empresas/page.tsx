import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function EmpresasPage() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="empresas" />
    </RequireAuth>
  );
}
