import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function Page() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="dashboard" />
    </RequireAuth>
  );
}