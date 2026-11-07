import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { User } from '../types'
import { ProfileModal } from './ProfileModal'

const updateUser = vi.fn()
let currentUser: Partial<User>

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: currentUser, updateUser, logout: vi.fn() }),
}))
vi.mock('../api/customThemes', () => ({
  activateCustomTheme: vi.fn(),
  createCustomTheme: vi.fn(),
  deleteCustomTheme: vi.fn(),
  listCustomThemes: vi.fn().mockResolvedValue([]),
  updateCustomTheme: vi.fn(),
}))
const updateDmEmailNotifications = vi.fn()
vi.mock('../api/auth', () => ({
  changePassword: vi.fn(),
  listSessions: vi.fn().mockResolvedValue([]),
  me: vi.fn(),
  removeAvatar: vi.fn(),
  revokeSession: vi.fn(),
  updateDmEmailNotifications: (enabled: boolean) => updateDmEmailNotifications(enabled),
  updateEmojiScale: vi.fn(),
  updateProfile: vi.fn(),
  updateTextScale: vi.fn(),
  updateTheme: vi.fn(),
  uploadAvatar: vi.fn(),
}))

beforeEach(() => {
  currentUser = {
    id: 'u1',
    username: 'alice',
    display_name: null,
    theme: 'dark',
    text_scale: 'normal',
    emoji_scale: 'normal',
    avatar_filename: null,
    appear_offline: false,
    dm_email_notifications: true,
  }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ProfileModal direct-message email toggle', () => {
  it('reflects the saved setting', () => {
    render(<ProfileModal onClose={() => {}} />)
    const toggle = screen.getByRole('checkbox', { name: 'Email me about direct messages' }) as HTMLInputElement
    expect(toggle.checked).toBe(true)

    cleanup()
    currentUser = { ...currentUser, dm_email_notifications: false }
    render(<ProfileModal onClose={() => {}} />)
    expect(
      (screen.getByRole('checkbox', { name: 'Email me about direct messages' }) as HTMLInputElement).checked,
    ).toBe(false)
  })

  it('saves the new value and updates the signed-in user', async () => {
    const updated = { ...currentUser, dm_email_notifications: false }
    updateDmEmailNotifications.mockResolvedValue(updated)
    render(<ProfileModal onClose={() => {}} />)

    fireEvent.click(screen.getByRole('checkbox', { name: 'Email me about direct messages' }))

    expect(updateDmEmailNotifications).toHaveBeenCalledWith(false)
    await waitFor(() => expect(updateUser).toHaveBeenCalledWith(updated))
  })

  it('shows an error and leaves the user unchanged when saving fails', async () => {
    updateDmEmailNotifications.mockRejectedValue(new ApiError(500, 'Server exploded'))
    render(<ProfileModal onClose={() => {}} />)

    fireEvent.click(screen.getByRole('checkbox', { name: 'Email me about direct messages' }))

    expect(await screen.findByText('Server exploded')).toBeTruthy()
    expect(updateUser).not.toHaveBeenCalled()
  })
})
