import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function ConfiguracionPage() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="configuracion" />
    </RequireAuth>
  );
}
