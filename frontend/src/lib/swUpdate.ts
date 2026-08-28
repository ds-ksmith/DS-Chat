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
  // #58: this used to be a bare `void registration?.update()` -- if the
  // fetch failed (most plausible right when it's triggered by a WS
  // reconnect, i.e. the network just flapped from a backend restart), the
  // rejection vanished with nothing to catch it and nothing logged. The
  // only other trigger was an hourly interval, so a client that hit this
  // at the wrong moment could sit stale for up to an hour with zero trace
  // of why. This doesn't fix a bad network, but it stops the failure from
  // being silent, and callers still don't need to handle anything.
  registration?.update().catch((err: unknown) => {
    console.error('Service worker update check failed', err)
  })
}
