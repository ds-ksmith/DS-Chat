import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { completePasswordReset, validateResetToken } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../context/AuthContext'
import logo from '../assets/logo.png'
import './LoginPage.css'

export function ResetPasswordPage() {
  const { user, updateUser } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''

  const [checking, setChecking] = useState(true)
  const [validationError, setValidationError] = useState<string | null>(null)

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!token) {
      setValidationError('This reset link is missing a token.')
      setChecking(false)
      return
    }
    validateResetToken(token)
      .catch((err) => {
        setValidationError(err instanceof ApiError ? err.message : 'This reset link is invalid.')
      })
      .finally(() => setChecking(false))
  }, [token])

  if (user) return <Navigate to="/rooms" replace />

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (password !== confirmPassword) {
      setError("Passwords don't match")
      return
    }
    setSubmitting(true)
    try {
      const loggedInUser = await completePasswordReset(token, password)
      updateUser(loggedInUser)
      navigate('/rooms')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          <img src={logo} alt="" />
          <span>DS Chat</span>
        </div>

        {checking && <p className="login-copy">Checking your reset link…</p>}

        {!checking && validationError && (
          <>
            <p className="login-copy">{validationError}</p>
            <p className="login-copy">Request a new reset link and try again.</p>
          </>
        )}

        {!checking && !validationError && (
          <>
            <p className="login-copy">Choose a new password for your account.</p>
            <form className="login-form" onSubmit={handleSubmit}>
              <label>
                New password
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  autoFocus
                />
              </label>
              <label>
                Confirm new password
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  minLength={8}
                />
              </label>
              {error && <p className="login-error">{error}</p>}
              <button type="submit" className="btn-primary" disabled={submitting}>
                {submitting ? 'Saving…' : 'Reset password'}
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
