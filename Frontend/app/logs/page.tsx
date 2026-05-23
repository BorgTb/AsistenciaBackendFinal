import { RequireAuth } from '@/components/RequireAuth';
import { SasDashboard } from '@/components/SasDashboard';

export default function LogsPage() {
  return (
    <RequireAuth>
      <SasDashboard initialSection="logs" />
    </RequireAuth>
  );
}