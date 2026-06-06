// ============================================================
// DialEasypro — App.tsx
// Routing + auth guard + React Query provider
// ============================================================
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { Layout } from './components/Layout';
import { ToastProvider } from './components/ui';
import { useAuthStore } from './store/authStore';

// Pages
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Leads from './pages/Leads';
import LeadDetail from './pages/LeadDetail';
import AgentsPage from './pages/AgentsPage';
import CallsPage from './pages/CallsPage';
import CommunicationsPage from './pages/CommunicationsPage';
import CampaignsPage from './pages/CampaignsPage';
import ReportsPage from './pages/ReportsPage';
import QueuesPage from './pages/QueuesPage';
import IntegrationsPage from './pages/IntegrationsPage';
import SettingsPage from './pages/SettingsPage';
import LeadImportPage from './pages/LeadImportPage';
import ProfilePage from './pages/ProfilePage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

function AuthGuard() {
  const { isAuthenticated } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return (
    <Layout>
      <Outlet />
    </Layout>
  );
}

function PublicGuard() {
  const { isAuthenticated } = useAuthStore();
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            {/* Public routes */}
            <Route element={<PublicGuard />}>
              <Route path="/login" element={<Login />} />
            </Route>

            {/* Root redirect */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />

            {/* Protected routes */}
            <Route element={<AuthGuard />}>
              <Route path="/dashboard"         element={<Dashboard />} />
              <Route path="/leads"             element={<Leads />} />
              <Route path="/leads/import"      element={<LeadImportPage />} />
              <Route path="/leads/:id"         element={<LeadDetail />} />
              <Route path="/calls"             element={<CallsPage />} />
              <Route path="/queues"            element={<QueuesPage />} />
              <Route path="/agents"            element={<AgentsPage />} />
              <Route path="/communications"    element={<CommunicationsPage />} />
              <Route path="/campaigns"         element={<CampaignsPage />} />
              <Route path="/reports"           element={<ReportsPage />} />
              <Route path="/integrations"      element={<IntegrationsPage />} />
              <Route path="/settings"          element={<SettingsPage />} />
              <Route path="/profile"           element={<ProfilePage />} />
            </Route>

            {/* 404 fallback */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
      {typeof import.meta !== "undefined" && (import.meta as { env?: { DEV?: boolean } }).env?.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
