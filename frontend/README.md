# KeepItTalking frontend (Phase 1)

React + Vite PWA. Login, room list, and chat views wired to the backend's
REST API and `/ws/chat` WebSocket endpoint. See [`../README.md`](../README.md)
and [`../backend/README.md`](../backend/README.md) for full local setup.

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

Generates the PWA manifest and service worker via `vite-plugin-pwa` into `dist/`.

## Layout

```
src/
  main.tsx, App.tsx        routes: /login, /rooms, /rooms/:roomId
  api/                       fetch wrappers (client, auth, rooms)
  ws/useChatSocket.ts          WebSocket hook (join/send/receive)
  context/AuthContext.tsx        current-user state, hydrated via GET /api/auth/me
  components/                      ProtectedRoute, RoomListItem, MessageList, MessageInput
  pages/                             LoginPage, RoomListPage, ChatRoomPage
```
