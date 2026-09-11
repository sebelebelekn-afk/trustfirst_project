# TrustFirst for iOS

A native SwiftUI app, not a webview. It talks to the same backend the web app
does: Supabase directly for data (under the same row-level security), and the
Django service for anything that needs a server-held secret.

## Requirements

- **Xcode 26 or later**, and the iOS 26 SDK.
- A Mac. There is no way around this one.

The deployment target is iOS 26 and there are no compatibility branches. That
is deliberate: Liquid Glass is the design here, not a finish applied to it, and
every `if #available` fallback would be a second, worse design to maintain.

## Opening it

```sh
open ios/TrustFirst.xcodeproj
```

Then pick a simulator and run. There are **no package dependencies** — nothing
to resolve, nothing to install. Supabase is reached over plain REST by a small
client in `Core/Networking`, which is why.

If Xcode refuses to open the project file, regenerate it instead of repairing
it by hand:

```sh
brew install xcodegen
cd ios && xcodegen generate
```

`TrustFirst.xcodeproj` uses Xcode 26 *synchronized folders*: every file under
`TrustFirst/` is part of the target automatically. Adding a Swift file means
saving it to disk — the project file never needs editing.

## Layout

```
TrustFirst/
  App/            the app entry point and the three-tab shell
  DesignSystem/   colours, type, metrics, and the Liquid Glass controls
  Core/
    Config/       what the server tells the app on boot
    Networking/   HTTP, and the typed PostgREST query builder
    Auth/         sign-in, token refresh, Keychain
    Models/       rows as the database stores them
  Features/       one folder per screen
```

## How it reaches the backend

- **`GET /api/config/`** on boot hands back the Supabase URL and anon key, the
  media host, and the payment mode. Nothing is hard-coded, so rotating any of
  them never needs a new build through review.
- **Data** goes straight to Supabase over PostgREST with the signed-in user's
  access token. The database decides what is visible; the app is never trusted.
- **Sign-in by username** goes through Django, because turning a username into
  an email needs the service key and that key never leaves the server. Sign-in
  by email goes straight to Supabase.
- **Refresh tokens live in the Keychain**, not UserDefaults, and are marked
  `ThisDeviceOnly` so they do not travel in a backup.

## Groups

A group is what a community is on Reddit. `posts.group_id` is nullable, so a
post is either inside a group or on the open feed, and the app treats both as
real destinations. Groups drive three things:

- **The home feed** is the posts in the groups you belong to, nothing else.
- **The ☰ drawer** lists those groups and opens each one.
- **The composer** asks which group a post is going to before it will post.

Groups have no uploaded icon in this database — they have an emoji and a
colour — so `TFGroupIcon` draws that, falling back to a colour derived from the
group's id so the same group is the same colour on every device.

## What is not built yet

- **Realtime.** Messages, calls, live rooms and notification badges all need a
  websocket; the REST layer here does not cover it.
- **Media upload** through the R2 presign endpoint. The composer posts text.
- **Replies and About** on the profile, and the whole of clips, stories, DMs,
  channels, live and the wallet.

## Two things the database would need changing for

Neither is a bug. Both are decisions, and the app is written to the schema as
it stands rather than to a schema that might exist later.

- **Posts have no title.** The web app stores a post as `text_content` and
  nothing else, so the composer is body-only. A Reddit-style Title field would
  need a `title` column on `posts`.
- **Notifications carry no group.** The `notifications` row has `message`,
  `preview_text`, `type` and an actor, but nothing linking it to a post or a
  group — so "replied to your post in <group>" cannot be rendered from the
  row. The app shows the server's own `message` instead, which is the only
  text that knows the context. Attributing a group there needs the server to
  put it in `message`, or a new column.

## One thing to settle before the wallet is built

Coins are bought through Yoco on web and Android. On iOS, Apple requires
in-app purchase for digital goods and takes a commission on them. That is a
different flow, not a restyled one, and it is worth deciding before the wallet
screens are written rather than after App Review sees them.
