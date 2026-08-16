import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { requestPasswordReset } from '../api/auth'
import { useAuth } from '../context/AuthContext'
import logo from '../assets/logo.png'
import './LoginPage.css'

export function ForgotPasswordPage() {
  const { user } = useAuth()
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)

  if (user) return <Navigate to="/rooms" replace />

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      await requestPasswordReset(email)
    } catch {
      // Fall through to the generic message regardless -- the request
      // itself never reveals whether the email is registered.
    } finally {
      setSubmitting(false)
      setSent(true)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          <img src={logo} alt="" />
          <span>DS Chat</span>
        </div>

        {sent ? (
          <p className="login-copy">
            If an account exists for that email, a password reset link is on its way. The link
            expires in 15 minutes.
          </p>
        ) : (
          <>
            <p className="login-copy">Enter your account email and we'll send a reset link.</p>
            <form className="login-form" onSubmit={handleSubmit}>
              <label>
                Email
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                />
              </label>
              <button type="submit" className="btn-primary" disabled={submitting}>
                {submitting ? 'Sending…' : 'Send reset link'}
              </button>
            </form>
          </>
        )}

        <Link to="/login" className="login-link">
          Back to log in
        </Link>
      </div>
    </div>
  )
}
