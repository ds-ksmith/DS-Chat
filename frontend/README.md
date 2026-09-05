# DS Chat frontend

React 19 + TypeScript + Vite PWA. The full client for DS Chat: auth and
invite-based signup, room CRUD with roles/invites, direct messages,
real-time WebSocket chat (Markdown, @mentions, reactions, built-in and
custom emoji, image/video/file attachments with previews, message editing
and deletion), unread indicators and presence, per-user theming (presets
plus a custom theme builder), Web Push/email notifications and a desktop-
notification bridge, an active-sessions view for managing where you're
logged in, offline caching and an auto-update banner via a custom service
worker, and a site-admin portal — wired to the backend's REST API and
`/ws/chat` WebSocket endpoint. See [`../README.md`](../README.md) and
[`../backend/README.md`](../backend/README.md) for full local setup.

## Dev

```bash
npm install
npm run dev
```

The dev server proxies `/api` and `/ws` to `http://localhost:8000` (see
`vite.config.ts`), so the backend must be running for anything beyond the
login page to work.

## Build

```bash
npm run build
```

`vite-plugin-pwa` runs in `injectManifest` mode: instead of generating a
service worker, it precaches the build output (`src/sw.ts`'s
`precacheAndRoute`) and injects that manifest into the hand-written worker at
`src/sw.ts`. `injectManifest` mode was needed over the default `generateSW`
because push/`notificationclick` listeners have to be hand-written into the
worker.

## Layout

```
src/
  main.tsx, App.tsx        routes: /login, /signup, /forgot-password, /reset-password,
                             /rooms, /rooms/:roomId, /admin (AdminRoute-gated), /help;
                             mounts UpdateBanner globally, ChatSocketProvider and
                             CustomEmojiProvider once authed
  types.ts                  shared request/response/WS-envelope types, mirroring the
                             backend's Pydantic schemas

  api/                      fetch wrappers, one file per backend resource: client
                              (base fetch/error handling), auth (incl. active sessions),
                              signup, rooms (incl. DMs), users, bots, webhooks, push,
                              admin, customThemes, customEmoji, uploads
  ws/useChatSocket.ts        the WebSocket hook: connect/reconnect with backoff,
                              join/leave rooms, send/edit/delete/react, visibility-gated
                              presence, triggers an SW update check on reconnect
  context/
    AuthContext.tsx            current-user state, hydrated via GET /api/auth/me
    ChatSocketContext.tsx      shares one useChatSocket instance across the app
    CustomEmojiContext.tsx     fetches the site's custom emoji once, exposes a
                                 shortcode lookup + a refresh() called after upload/delete

  lib/
    avatar.ts                  deterministic accent-color cycling for avatars
    emoji.ts, emojiNames.ts,
    emojiShortcodes.ts, recentEmoji.ts    emoji picker data + recency tracking
    fileSize.ts                 human-readable byte formatting
    lastUser.ts                 cached "who was I last logged in as" for offline shell render
    messageGrouping.ts          groups consecutive messages by sender/time, presence lookup
    push.ts                     PushManager subscribe/unsubscribe, VAPID key conversion,
                                  timeout-guarded so a browser that never settles the
                                  permission prompt can't leave the UI stuck forever
    swUpdate.ts                  bridges the SW registration to useChatSocket's reconnect hook
    theme.ts                     applies preset/custom themes as CSS custom properties

  hooks/
    useEscapeKey.ts              Escape-to-close for modals/popovers
    useOnlineStatus.ts           navigator.onLine, for the OfflineBanner
    useResizableWidth.ts         drag-to-resize (sidebar/panel widths)
    useWindowWidth.ts            viewport width, for responsive sidebar/pane layout

  components/
    ProtectedRoute.tsx, AdminRoute.tsx        auth/site-admin route guards
    TopBar.tsx, Sidebar.tsx, RoomRow.tsx        room list chrome (DMs and Rooms as
                                                  independently collapsible sections)
    ChatPane.tsx, MessageList.tsx, Composer.tsx    chat view: history+live merge,
                                                     message rendering (incl. deleted-message
                                                     tombstones), composer/attach/send
    MessageContent.tsx, MentionAutocomplete.tsx    Markdown rendering (mentions, room
                                                     links, custom emoji `:shortcode:`,
                                                     heading ids, sub/superscript) +
                                                     @mention highlighting/autocomplete
    ImageLightbox.tsx, VideoLightbox.tsx,
    FilePreviewModal.tsx                           attachment viewers (image/video/PDF/
                                                     text/Markdown)
    EmojiPicker.tsx, CustomEmojiUploadModal.tsx     reaction/composer emoji picker
                                                      (built-in + site's custom emoji) and
                                                      its upload dialog
    RoomInfoPanel.tsx                              room details/members/roles/email-
                                                     notification-toggle panel
    NewRoomModal.tsx, BrowseRoomsModal.tsx, UserPicker.tsx    room creation/discovery, member
                                                                picking (also how a DM starts)
    ProfileModal.tsx, ThemeBuilderModal.tsx, CustomThemePreview.tsx
                                                    profile settings (incl. active-sessions
                                                    list) + the custom theme editor (opened
                                                    in its own wide dialog) with a live,
                                                    hoverable mockup of the real UI
    RoomAvatar.tsx, UserAvatar.tsx                 avatar rendering (incl. presence dot)
    OfflineBanner.tsx, UpdateBanner.tsx            connectivity state / new-version-available prompt

  pages/
    LoginPage.tsx, SignupPage.tsx, ForgotPasswordPage.tsx, ResetPasswordPage.tsx
    ChatShellPage.tsx, AdminPage.tsx, HelpPage.tsx

  styles/tokens.css          design tokens (default theme: colors, spacing, etc.)
  sw.ts                      custom service worker (injectManifest): app-shell
                               precache + NetworkFirst runtime caching, push/notificationclick
                               handlers, SKIP_WAITING messaging for the update-prompt flow
```

## License

AGPL-3.0-or-later — see [`../LICENSE`](../LICENSE).
