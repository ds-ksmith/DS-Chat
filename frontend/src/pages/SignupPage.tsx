import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { completeSignup, validateSignupToken } from '../api/signup'
import { useAuth } from '../context/AuthContext'
import logo from '../assets/logo.png'
import './LoginPage.css'

export function SignupPage() {
  const { user, updateUser } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''

  const [checking, setChecking] = useState(true)
  const [email, setEmail] = useState<string | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!token) {
      setValidationError('This invite link is missing a token.')
      setChecking(false)
      return
    }
    validateSignupToken(token)
      .then((result) => setEmail(result.email))
      .catch((err) => {
        setValidationError(err instanceof ApiError ? err.message : 'This invite link is invalid.')
      })
      .finally(() => setChecking(false))
  }, [token])

  if (user) return <Navigate to="/rooms" replace />

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const newUser = await completeSignup(token, username, password)
      updateUser(newUser)
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
          <span>KeepItTalking</span>
        </div>

        {checking && <p className="login-copy">Checking your invite…</p>}

        {!checking && validationError && (
          <>
            <p className="login-copy">{validationError}</p>
            <p className="login-copy">Ask whoever invited you to send a new invite.</p>
          </>
        )}

        {!checking && !validationError && (
          <>
            <p className="login-copy">Set up your account for {email}.</p>
            <form className="login-form" onSubmit={handleSubmit}>
              <label>
                Username
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  minLength={3}
                  maxLength={50}
                  autoFocus
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                />
              </label>
              {error && <p className="login-error">{error}</p>}
              <button type="submit" className="btn-primary" disabled={submitting}>
                Create account
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
