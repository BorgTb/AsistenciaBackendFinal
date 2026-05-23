import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function PersonasPage() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="personas" />
    </RequireAuth>
  );
}