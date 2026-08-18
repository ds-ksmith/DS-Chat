import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ChatSocketProvider } from './context/ChatSocketContext'
import { AdminRoute } from './components/AdminRoute'
import { DesktopNotificationBridge } from './components/DesktopNotificationBridge'
import { ProtectedRoute } from './components/ProtectedRoute'
import { UpdateBanner } from './components/UpdateBanner'
import { LoginPage } from './pages/LoginPage'
import { SignupPage } from './pages/SignupPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { ChatShellPage } from './pages/ChatShellPage'
import { AdminPage } from './pages/AdminPage'
import { HelpPage } from './pages/HelpPage'

function AppRoutes() {
  const routes = (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        path="/rooms"
        element={
          <ProtectedRoute>
            <ChatShellPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/rooms/:roomId"
        element={
          <ProtectedRoute>
            <ChatShellPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <AdminRoute>
            <AdminPage />
          </AdminRoute>
        }
      />
      <Route
        path="/help"
        element={
          <ProtectedRoute>
            <HelpPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/rooms" replace />} />
    </Routes>
  )

  // Only while actually logged in -- and keyed by user id so switching
  // which account is logged in (same tab) tears down and re-establishes a
  // fresh connection rather than an old one lingering under a new
  // identity. Wraps every authenticated route (not just ChatShellPage),
  // since the connection backs the presence indicator and cross-page
  // signals (e.g. "added to a room") that matter regardless of which page
  // is currently open.
  const { user } = useAuth()
  if (!user) return routes
  return (
    <ChatSocketProvider key={user.id}>
      <DesktopNotificationBridge />
      {routes}
    </ChatSocketProvider>
  )
}

function App() {
  return (
    <AuthProvider>
      <UpdateBanner />
      <AppRoutes />
    </AuthProvider>
  )
}

export default App
