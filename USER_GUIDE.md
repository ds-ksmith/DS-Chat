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

## Formatting

Messages support Markdown:

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
reaction to it. Hovering a pill shows who reacted.

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

Room admins and owners see additional management options here that
aren't covered in this guide.

## Staying up to date

If your connection drops, a banner lets you know you're offline and
working from cached data — sending is disabled until you're back online.

When a new version of DS Chat has been deployed, a banner offers a
**Reload** button to pick it up immediately, instead of waiting for your
next natural page refresh.
