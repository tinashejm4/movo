# Intracity WebSockets

Intracity WebSockets are notification channels. REST remains the source of
truth for current-package, package-detail, driver, and payment data.

## Prerequisites

- Use the user's **access JWT** returned by login or token refresh. Do not send
  the refresh token.
- Add [`web_socket_channel`](https://pub.dev/packages/web_socket_channel) to
  Flutter if it is not already present.
- Use `wss` in production and ensure reverse-proxy logs redact the `token`
  query parameter.

## Current-packages dashboard subscription

Connect once while the authenticated customer session and dashboard/home state
are active:

```text
wss://api.example.com/ws/intracity/assignments/?token=<access_jwt>
```

For local HTTP development:

```text
ws://10.0.2.2:8000/ws/intracity/assignments/?token=<access_jwt>
```

The global URL is scoped on the server to the authenticated user's private
current-packages group. It no longer emits full `package_assigned` payloads.

Immediately after an accepted connection, the server sends:

```json
{
  "event": "connected",
  "data": {
    "group": "current_packages_user_42",
    "package_id": null,
    "subscribed": true
  }
}
```

`subscribed: false` means the connection was accepted but the Channels group
could not be joined. Continue using REST and retry the socket instead of
treating it as live.

When the user's current packages change, the server sends only an invalidation
notification:

```json
{
  "event": "current_packages_changed",
  "data": {
    "package_id": 123,
    "reason": "assigned"
  }
}
```

`reason` is one of `created`, `assigned`, `picked_up`, `cancelled`, or
`delivered`. On every such event, debounce overlapping refreshes and fetch all
data again from:

```text
GET /api/intracity/current-packages/
```

Do not merge the event body into cached packages. The event can be missed or
replayed, and a cancellation may mean the package must be removed from the
list.

Also refresh the REST endpoint immediately after a successful connection or
reconnection. Close the global socket on logout and replace it after the access
token or signed-in user changes.

### Flutter message handling

```dart
Future<void> onMessage(dynamic rawMessage) async {
  final message = jsonDecode(rawMessage as String) as Map<String, dynamic>;
  if (message['event'] != 'current_packages_changed') return;

  // Debounce this in the owning Riverpod/controller so a burst of lifecycle
  // events produces one authoritative REST refresh.
  // refresh() calls getCurrentPackages(), which follows every response page.
  await ref.read(currentPackagesProvider.notifier).refresh();
}
```

## Package-specific assignment subscription

Package-detail/tracking screens continue to use the package-specific URL:

```text
wss://api.example.com/ws/intracity/assignments/<package_id>/?token=<access_jwt>
```

Connect only while that package screen is visible and close the socket when
leaving it. The user must be the package sender, receiver, or assigned biker.

When dispatch assigns a biker, this socket still sends:

```json
{
  "event": "package_assigned",
  "data": {
    "package_id": 123,
    "slug": "mov-abc123",
    "biker_id": 9,
    "biker_name": "Tendai Moyo",
    "assigned_at": "2026-07-28T10:15:30+02:00"
  }
}
```

Use this event only as a prompt to refresh the package-detail REST endpoint.

## Authentication and reconnection

The server closes the handshake with:

| Close code | Meaning |
| --- | --- |
| `4401` | JWT missing, invalid, expired, is a refresh token, or belongs to an inactive user |
| `4403` | JWT is valid but the user cannot view the requested package-specific subscription |

- On `4401`, refresh the access token normally and create a new WebSocket URL.
- On package-specific `4403`, stop reconnecting and show the normal unavailable
  or unauthorized package state.
- For transient closures, reconnect with bounded exponential backoff.
- Keep REST refresh-on-resume behavior because backgrounded apps can miss
  WebSocket notifications.

The sockets accept no application messages from Flutter; both are
server-to-client only.
