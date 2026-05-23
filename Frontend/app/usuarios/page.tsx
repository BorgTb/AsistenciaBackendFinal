import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function UsuariosPage() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="usuarios" />
    </RequireAuth>
  );
}
