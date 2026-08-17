// Bridges the service worker registration (owned by UpdateBanner, which
// mounts outside ChatSocketProvider -- see App.tsx) out to code that has no
// other way to reach it, namely useChatSocket.ts's reconnect handler, which
// wants to trigger an update check whenever the WS reconnects (a reliable
// signal the backend just restarted, i.e. a deploy happened).
let registration: ServiceWorkerRegistration | null = null

export function setSwRegistration(reg: ServiceWorkerRegistration): void {
  registration = reg
}

export function checkForUpdate(): void {
  void registration?.update()
}
