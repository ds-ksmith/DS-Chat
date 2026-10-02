const KEY = 'ds-chat-formatting-toolbar-open'

// Collapsed unless the user has opened it before -- and remembered, because
// Composer remounts on every room switch and would otherwise snap shut each
// time.
export function getFormattingToolbarOpen(): boolean {
  try {
    return localStorage.getItem(KEY) === 'true'
  } catch {
    return false
  }
}

export function setFormattingToolbarOpen(open: boolean): void {
  try {
    localStorage.setItem(KEY, String(open))
  } catch {
    // storage unavailable (private browsing, quota) -- the toolbar just
    // won't remember its state, not fatal.
  }
}
