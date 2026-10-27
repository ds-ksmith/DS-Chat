# DS Chat — User Guide

A quick reference for everyday use: sending messages, organizing rooms,
attachments, notifications, and personalizing your account.

## Contents

- [Getting started](#getting-started)
- [Rooms](#rooms)
- [Direct messages](#direct-messages)
- [Sending messages](#sending-messages)
- [Formatting](#formatting)
- [Mentions and room links](#mentions-and-room-links)
- [Attachments](#attachments)
- [Reactions and custom emoji](#reactions-and-custom-emoji)
- [Editing and deleting a message](#editing-and-deleting-a-message)
- [Presence and notifications](#presence-and-notifications)
- [Your profile](#your-profile)
- [Room details](#room-details)
- [Integrations](#integrations)
- [Active sessions](#active-sessions)
- [Staying up to date](#staying-up-to-date)

## Getting started

DS Chat is invite-only — there's no public sign-up page. You'll either be
given an account directly, or you'll receive an email invite with a
link. Opening that link lets you pick a username and password; once
you submit it, you're signed in automatically.

If you forget your password, use **Forgot password?** on the login
screen. You'll get an email with a reset link that's valid for 15
minutes.

## Rooms

Rooms are where conversations happen — similar to channels in other chat
apps. The sidebar on the left lists every room you belong to, with a
search box at the top to filter by name.

- **Create a room**: click the **+** button above the room list. Give it a
  name and, optionally, a description. You become that room's owner.
- **Browse rooms**: click **Browse rooms** to see every *open* room on the
  site and join any of them directly.
- **Private rooms**: a room marked private (shown with a lock icon) isn't
  listed in Browse rooms — you can only get in by being added by an
  owner or admin of that room.
- **Unread indicators**: a room with new activity shows a dot next to its
  name — a plain dot for unread messages, a highlighted dot if you were
  specifically @mentioned.
- **Collapsible sections**: the **Direct Messages** and **Rooms** headers in
  the sidebar can be collapsed to hide their contents — click the header to
  toggle. Your choice is remembered.

## Direct messages

Click **People** to see everyone on the site and start a 1:1 conversation
with someone — it opens (or reopens, if you've messaged them before)
under **Direct Messages** in the sidebar. There's only ever one
conversation per pair of people, however many times you start it.

You can hide a conversation you're done with (its own menu, or from its
**Room details** panel) without deleting anything — it drops out of your
sidebar but reappears automatically the moment the other person sends a
new message, or if you message them again yourself.

## Sending messages

Type in the message box at the bottom of a room and press **Enter** to
send. Use **Shift+Enter** to add a line break without sending.

Each message shows when it was sent, in your local time. Messages from today
show just the time; older ones add the day — "Yesterday 4:04 PM", a weekday
like "Mon 4:04 PM" for the past week, then the date ("Oct 2, 4:04 PM", with
the year if it's not this one). Hover a time to see the full date.

## Formatting

Messages support Markdown. Prefer buttons to typing the syntax? Click the
**Aa** button next to the emoji button in the composer to open a formatting
toolbar — it inserts the markdown below into your message for you (select some
text first to wrap it, or click a button again to take the formatting back
off). It stays collapsed until you open it, and remembers your choice.

Or type it yourself:

- `**bold**`, `*italic*`, `~~strikethrough~~`
- `` `inline code` `` and fenced code blocks (three backticks)
- `> blockquotes`
- `-` or `1.` for bulleted/numbered lists
- `[link text](https://example.com)` — or just paste a bare URL and it
  becomes clickable automatically
- `#`, `##`, `###` for headings — add `{#custom-id}` at the end of a
  heading line to control its link anchor instead of the auto-generated one
- `~sub~` and `^sup^` for subscript and superscript

Pasting a link on its own often also generates a preview card underneath
your message, pulled from that page's title/description/image, when the
page provides one.

Emoji: click the 🙂 button in the composer to open the emoji picker, or
type a shortcode like `:tada:` and it's converted automatically once you
send. The picker remembers your recently-used emoji and has a search box —
see [Reactions and custom emoji](#reactions-and-custom-emoji) for uploading
your own.

## Mentions and room links

Type `@` followed by a few letters of someone's username to open an
autocomplete of that room's members — pick one (or press Enter/Tab) to
insert a mention. Mentioning someone highlights the message for them and
marks the room specially in their sidebar, even if they're not currently
looking at it.

Type `#` followed by a few letters of a room name to do the same for
rooms you belong to — it inserts a clickable link that takes anyone who
can see the message (and is a member of that room) straight to it.

## Attachments

Click the paperclip icon to attach a file, or just drag a file onto the
message box and drop it. Images show as an inline thumbnail — click one
to view it full-size. Common video formats (MP4, WebM, Ogg) play inline
too, with a button to expand to a larger view; other files show as a
small card with the filename and size — `.txt`, `.md`, and `.pdf` files
open in a preview without leaving the room, everything else downloads
when clicked.

There's a server-configured maximum file size — if a file is too large,
you'll see an error before it uploads.

## Reactions and custom emoji

Hover over a message and click the 🙂 icon in its action row to react
with an emoji. Reactions from everyone appear as small pills under the
message with a count; click an existing pill to add or remove your own
reaction to it. Hovering a pill shows who reacted. Once a message has
reactions, a small **+🙂** button at the end of the row of pills lets you
add a different emoji without going back to the action row.

Anyone can add a custom emoji: open the emoji picker (the 🙂 button, either
in the composer or on a message) and click **+ Add** in the **Custom**
section. Give it a short name and an image — it's then usable by everyone,
both as a reaction and inline in message text via `:your-name:`, right
alongside the built-in picker. You can remove a custom emoji you uploaded
(or any of them, if you're a site admin) from the same picker.

## Editing and deleting a message

You can edit any message you sent: hover it and click **Edit**, make your
changes, then press **Enter** to save or **Escape** to cancel. Clicking
away also saves. Edited messages are marked *(edited)*.

To delete a message you sent, hover it and click **Delete**. It's replaced
with a "message deleted" placeholder rather than disappearing outright, so
the conversation doesn't visibly shift for anyone else reading it.

## Presence and notifications

Everyone's avatar shows a small status dot — green for online, grey for
offline — based on whether they currently have the app open. If you'd
rather not broadcast that you're active, open your account menu (click
your avatar, top right) and choose **Appear offline**.

The same menu has a notifications toggle:

- In a regular browser, turning it on asks your browser for permission
  and subscribes you to push notifications for messages in rooms you're
  not actively looking at.
- In DS Chat Desktop, the same toggle controls native desktop
  notifications instead — no browser permission prompt needed. You'll
  get a notification whenever the app is minimized *or* simply not the
  focused window, even if it's still open somewhere on screen.

You'll also get an email if someone messages you in a direct conversation
while you're genuinely offline — no setup needed. For regular rooms,
email is opt-in per room: open a room's **Room details** panel and turn
on **Email notifications** to get emailed on that room's first unread
message and on every `@mention`, while you're offline.

## Your profile

Open your account menu and choose **Profile settings** to:

- Upload or remove a profile photo
- Set a display name (shown instead of your username throughout the app)
- Pick a theme — Dark, Light, Midnight, Sunset, or build your own custom
  color scheme (create one, then customize each color; changes preview
  live)
- Change your password

## Active sessions

Profile settings also lists **Active sessions** — every device/browser
currently logged into your account, with its approximate location (IP
address) and when it was last active. If you see one you don't
recognize, click **Revoke** to sign it out immediately. Revoking your own
current device signs you out too.

## Room details

Click the info icon in a room's header to open its details panel, where
you can:

- See who else is in the room and their role (member/admin/owner)
- Turn on **Email notifications** for that room (see
  [Presence and notifications](#presence-and-notifications))
- Browse and re-download every file and image ever shared in the room,
  without scrolling back through history
- Leave the room — unless you're the owner, in which case ownership has
  to be transferred to someone else first

Room admins and owners see additional management options here, including
**Integrations** (see [Integrations](#integrations)).

## Integrations

DS Chat can exchange messages with other tools, three ways. The first two
are set up by a room's admins or owners; the third by a site admin.

| You want to… | Use |
| --- | --- |
| Post into a room from a script, CI job, or another service | [Incoming webhook](#incoming-webhooks) |
| Get notified elsewhere when a room's messages change | [Outgoing event subscription](#outgoing-event-subscriptions) |
| Have a program read and write messages as its own account | [Bot](#bots) |

Links in messages already get a preview card on their own, and Web Push
and email notifications work without any setup — see
[Presence and notifications](#presence-and-notifications).

### Incoming webhooks

An incoming webhook is a private URL that posts into one room.

1. Open the room's details panel (the info icon in the header) and expand
   **Integrations**. You need to be an admin or the owner of the room.
2. Under **Incoming webhooks**, add an optional description (such as
   "Deploy notices") and create it. The full URL is listed there whenever
   you need to copy it again.
3. Send a `POST` with a JSON body to that URL:

```bash
curl -X POST "https://chat.example.com/api/webhooks/incoming/<token>" \
  -H "Content-Type: application/json" \
  -d '{"content": "Deploy finished: **v2026.10.22** is live"}'
```

The message appears in the room right away, formatted like any other
(markdown works), attributed to whoever created the webhook, and it
notifies members the same way a typed message would. A successful post
returns `204`; an unknown or revoked URL returns `404`, and an archived
room returns `403`.

**Treat the URL like a password.** There's no other authentication: anyone
who has it can post into the room. If it leaks, click **Revoke** next to
it in the same panel and create a new one.

### Outgoing event subscriptions

An outgoing subscription sends DS Chat's events to a URL you control.

1. In the same **Integrations** panel, under **Outgoing event
   subscriptions**, enter the URL and tick the events you want:
   `message.created` (a new message) and/or `message.updated` (an edit).
2. Click **Add**. A **signing secret** appears once — copy it now, it
   won't be shown again.

Each event arrives as a `POST` with a JSON body:

```json
{
  "event": "message.created",
  "data": { "id": "…", "room_id": "…", "username": "alice", "content": "hello", "…": "…" }
}
```

To let you confirm a request really came from DS Chat, each one carries an
`X-DS-Chat-Signature: sha256=<hex>` header: the HMAC-SHA256 of the raw
request body, keyed with your signing secret. For example, in Python:

```python
import hashlib, hmac

expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
valid = hmac.compare_digest(expected, request_signature_header)
```

Things to know:

- **Delivery is best-effort.** Each event is tried once with a short
  timeout; if your endpoint is down or slow, that event is dropped and
  not retried. Don't rely on it as your only record of a conversation.
- **Only message creation and edits** are sent. Deletions, reactions,
  and joins don't generate events.
- **The URL must be publicly reachable.** Addresses that point to
  private or internal networks (localhost, `192.168.x.x`, and so on) are
  rejected when you add the subscription.
- **Revoke** removes a subscription immediately.

### Bots

A bot is an account for a program rather than a person. It signs in with
an API token instead of a password and uses the same interface as the
app itself, so it can read and write messages in real time.

Only **site admins** create bots: open the admin page, choose the **Bots**
tab, and click **Create bot**, then **Issue token** and pick what the
token may do:

- `read:messages` — read a room's message history
- `write:messages` — send, edit, and delete messages
- `manage:rooms` — recognized, but doesn't grant anything beyond what the
  bot's room role already allows

The token is shown once — copy it then. You can revoke it from the same
tab at any time.

A bot is held to the same rules as any member: it can only see and post
in rooms it belongs to, and its room role limits what it can do there.
The token can narrow that further, never widen it.

The bot connects to the WebSocket at `/ws/chat`, sending
`Authorization: Bearer <token>` with the connection, and then speaks
simple JSON messages:

```json
{"type": "join", "room_id": "<room id>"}
{"type": "message", "room_id": "<room id>", "content": "Hello from a bot"}
{"type": "edit", "room_id": "<room id>", "message_id": "<id>", "content": "Fixed"}
```

Messages from the room arrive on the same connection as they happen. The
same bearer token also works for the regular `/api/` endpoints, such as
fetching a room's history.

The server sends a `{"type": "ping"}` every 30 seconds to check a
connection is alive; a bot may ignore it, since bot connections are never
dropped for staying silent.

There is currently **no rate limiting** on bots (or anyone else), so keep
automation polite.

## Staying up to date

If your connection drops, a banner lets you know you're offline and
working from cached data — sending is disabled until you're back online.

When a new version of DS Chat has been deployed, a banner offers a
**Reload** button to pick it up immediately, instead of waiting for your
next natural page refresh.
