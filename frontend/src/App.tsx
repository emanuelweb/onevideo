import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth } from "./auth/RequireAuth";
import { RequireSuperadmin } from "./auth/RequireSuperadmin";
import { AppLayout } from "./components/AppLayout";
import AccountPage from "./pages/AccountPage";
import AdminPage from "./pages/AdminPage";
import DashboardPage from "./pages/DashboardPage";
import DeviceDetailPage from "./pages/DeviceDetailPage";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import ObsGuidePage from "./pages/ObsGuidePage";
import PricingPage from "./pages/PricingPage";
import RegisterPage from "./pages/RegisterPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/app" replace />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/registro" element={<RegisterPage />} />
          <Route path="/precios" element={<PricingPage />} />
          <Route
            path="/app"
            element={
              <RequireAuth>
                <AppLayout />
              </RequireAuth>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="dispositivos/:id" element={<DeviceDetailPage />} />
            <Route path="guia-obs" element={<ObsGuidePage />} />
            <Route path="cuenta" element={<AccountPage />} />
            <Route
              path="admin"
              element={
                <RequireSuperadmin>
                  <AdminPage />
                </RequireSuperadmin>
              }
            />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
