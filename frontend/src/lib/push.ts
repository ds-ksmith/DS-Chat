import { getVapidPublicKey, subscribePush, unsubscribePush } from '../api/push'

// A stuck permission prompt or service-worker-ready wait would otherwise
// leave TopBar's "Enable notifications" toggle permanently disabled with
// no feedback at all -- confirmed live on a fresh Windows/Edge install
// (never been used before): clicking it greyed the button out and never
// showed the OS permission prompt, with no error and no way out short of
// reloading. Most likely cause is Windows' own per-app notification
// permission being off for Edge (Settings > System > Notifications), which
// some Chromium versions handle by just never resolving the request
// instead of rejecting it -- but whatever the cause, the UI should never
// hang forever waiting on a browser API that may simply never settle.
class PushTimeoutError extends Error {}

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new PushTimeoutError(message)), ms)
    promise.then(
      (value) => {
        clearTimeout(timer)
        resolve(value)
      },
      (err: unknown) => {
        clearTimeout(timer)
        reject(err)
      },
    )
  })
}

function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = atob(base64)
  const outputArray = new Uint8Array(new ArrayBuffer(rawData.length))
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

export function isPushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window
}

export async function getPushSubscriptionStatus(): Promise<boolean> {
  if (!isPushSupported()) return false
  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.getSubscription()
  return subscription !== null
}

export async function subscribeToPush(): Promise<void> {
  if (!isPushSupported()) {
    throw new Error('Push notifications are not supported in this browser')
  }

  const permission = await withTimeout(
    Notification.requestPermission(),
    20_000,
    "The browser never responded to the notification permission request. Check this browser's notification permission for this site, and your OS-level notification settings for the browser, then try again.",
  )
  if (permission !== 'granted') {
    throw new Error('Notification permission was not granted')
  }

  const { public_key } = await getVapidPublicKey()
  if (!public_key) {
    throw new Error('Push notifications are not configured on the server')
  }

  const registration = await withTimeout(
    navigator.serviceWorker.ready,
    20_000,
    'The browser never finished setting up its background service worker. Try reloading the page.',
  )
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(public_key),
  })

  const json = subscription.toJSON()
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    throw new Error('Push subscription is missing required fields')
  }

  await subscribePush({
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
  })
}

export async function unsubscribeFromPush(): Promise<void> {
  if (!isPushSupported()) return
  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.getSubscription()
  if (!subscription) return
  await unsubscribePush(subscription.endpoint)
  await subscription.unsubscribe()
}
