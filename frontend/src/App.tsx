import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { LoginPage } from './pages/LoginPage'
import { ChatShellPage } from './pages/ChatShellPage'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
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
        <Route path="*" element={<Navigate to="/rooms" replace />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
