import React from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './store/auth'
import AppLayout from './layouts/AppLayout'
import { Loading } from './components/ui'

import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import DiscoveryPage from './pages/DiscoveryPage'
import PoliciesPage from './pages/PoliciesPage'
import PolicyDetailsPage from './pages/PolicyDetailsPage'
import PolicyCompanionPage from './pages/PolicyCompanionPage'
import IncidentPage from './pages/IncidentPage'
import ClaimsPage from './pages/ClaimsPage'
import ClaimCreatePage from './pages/ClaimCreatePage'
import ClaimDetailPage from './pages/ClaimDetailPage'
import DocumentCenterPage from './pages/DocumentCenterPage'
import ClaimReadinessPage from './pages/ClaimReadinessPage'
import ClaimTrackingPage from './pages/ClaimTrackingPage'
import JourneysPage from './pages/JourneysPage'
import JourneyInvestigationPage from './pages/JourneyInvestigationPage'
import JourneyRecoveryPage from './pages/JourneyRecoveryPage'
import NotificationsPage from './pages/NotificationsPage'
import EscalationsPage from './pages/EscalationsPage'
import EscalationDetailsPage from './pages/EscalationDetailsPage'

function RequireAuth({ children }: { children: React.ReactElement }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <div className="p-10"><Loading /></div>
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/discovery" element={<DiscoveryPage />} />
        <Route path="/policies" element={<PoliciesPage />} />
        <Route path="/policies/:id" element={<PolicyDetailsPage />} />
        <Route path="/policies/:id/companion" element={<PolicyCompanionPage />} />
        <Route path="/incidents" element={<IncidentPage />} />
        <Route path="/claims" element={<ClaimsPage />} />
        <Route path="/claims/new" element={<ClaimCreatePage />} />
        <Route path="/claims/:id" element={<ClaimDetailPage />} />
        <Route path="/claims/:id/documents" element={<DocumentCenterPage />} />
        <Route path="/claims/:id/readiness" element={<ClaimReadinessPage />} />
        <Route path="/claims/:id/tracking" element={<ClaimTrackingPage />} />
        <Route path="/journeys" element={<JourneysPage />} />
        <Route path="/journeys/:id/investigation" element={<JourneyInvestigationPage />} />
        <Route path="/journeys/:id/recovery" element={<JourneyRecoveryPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/escalations" element={<EscalationsPage />} />
        <Route path="/escalations/:id" element={<EscalationDetailsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
