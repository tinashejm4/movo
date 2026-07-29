# Intracity package-assignment WebSockets

Use this connection when the customer is viewing an active package and needs to
know as soon as a biker has been assigned. The socket is a notification channel:
the existing intracity REST endpoints remain the source of truth for package,
driver, and payment data.

## Prerequisites

- Use the user's **access JWT** returned by login or token refresh. Do not send
  the refresh token.
- Add [`web_socket_channel`](https://pub.dev/packages/web_socket_channel) to
  the Flutter app if it is not already present.
- Connect only while the package-detail/tracking screen is visible, then close
  the socket when leaving it.

## Endpoint

Subscribe to one package rather than the global endpoint:

```text
wss://api.example.com/ws/intracity/assignments/<package_id>/?token=<access_jwt>
```

For local HTTP development, use `ws` instead of `wss`:

```text
ws://10.0.2.2:8000/ws/intracity/assignments/<package_id>/?token=<access_jwt>
```

The server also exposes `/ws/intracity/assignments/`, but package-specific
subscriptions are the intended customer-app integration.

### Access rules

The socket accepts only a valid, active user's access JWT. For a particular
package, the user must be its sender, receiver, or assigned biker. The server
closes the handshake with:

| Close code | Meaning |
| --- | --- |
| `4401` | JWT missing, invalid, expired, refresh-token, or user inactive |
| `4403` | JWT is valid but the user cannot view this package |

The global endpoint is filtered by the same rule, so it only sends events for
packages that the connected user may access.

## Messages from the server

Immediately after an accepted connection:

```json
{
  "event": "connected",
  "data": {
    "group": "package_123",
    "package_id": 123,
    "subscribed": true
  }
}
```

`subscribed: false` means the connection is open but the Channels group could
not be joined (for example, the configured Redis channel layer is unavailable).
Continue with REST polling/retry rather than treating that socket as live.

When dispatch assigns a biker:

```json
{
  "event": "package_assigned",
  "data": {
    "package_id": 123,
    "slug": "mov-abc123",
    "is_fast_delivery": false,
    "biker_id": 9,
    "biker_name": "Tendai Moyo",
    "biker_phone": "0771234567",
    "assigned_at": "2026-07-28T10:15:30+02:00",
    "added_at": "2026-07-28T10:00:00+02:00"
  }
}
```

The socket currently accepts no application messages from Flutter; it is
server-to-client only.

## Flutter example

```dart
import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

class PackageAssignmentSocket {
  PackageAssignmentSocket({
    required this.apiBaseUri,
    required this.packageId,
    required this.accessToken,
    required this.onAssignment,
    required this.refreshPackage,
  });

  final Uri apiBaseUri;
  final int packageId;
  final String accessToken;
  final void Function(Map<String, dynamic> assignment) onAssignment;
  final Future<void> Function() refreshPackage;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;

  Future<void> connect() async {
    final scheme = apiBaseUri.scheme == 'https' ? 'wss' : 'ws';
    final uri = apiBaseUri.replace(
      scheme: scheme,
      path: '/ws/intracity/assignments/$packageId/',
      queryParameters: {'token': accessToken},
    );

    _channel = WebSocketChannel.connect(uri);
    await _channel!.ready;
    _subscription = _channel!.stream.listen(
      _onMessage,
      onError: (_) => _scheduleReconnect(),
      onDone: _scheduleReconnect,
    );
  }

  Future<void> _onMessage(dynamic rawMessage) async {
    final message = jsonDecode(rawMessage as String) as Map<String, dynamic>;
    if (message['event'] != 'package_assigned') return;

    final assignment = message['data'] as Map<String, dynamic>;
    onAssignment(assignment);

    // Refresh from REST: a WebSocket event can be missed while reconnecting,
    // and REST remains authoritative for the full package record.
    await refreshPackage();
  }

  void _scheduleReconnect() {
    // Implement bounded exponential backoff in the owning Riverpod/controller.
    // Do not reconnect after dispose or once the package is complete/cancelled.
  }

  Future<void> dispose() async {
    await _subscription?.cancel();
    await _channel?.sink.close();
  }
}
```

Example construction, where `apiBaseUri` is `https://api.example.com`:

```dart
final socket = PackageAssignmentSocket(
  apiBaseUri: Uri.parse(apiBaseUrl),
  packageId: package.packageId,
  accessToken: authState.accessToken,
  onAssignment: (assignment) {
    // Optionally update a temporary "driver found" UI state here.
  },
  refreshPackage: () => ref.read(packageDetailsProvider(package.packageId).notifier).refresh(),
);
await socket.connect();
```

## Reconnection and token refresh

- On `4401`, obtain a new access token through the normal refresh flow, then
  create a new WebSocket URL and reconnect. Do not use the refresh token in the
  URL.
- On `4403`, stop reconnecting and show the normal unavailable/not-authorized
  package state.
- For transient network closure, reconnect with bounded exponential backoff.
- When a connection is restored, refresh the package from REST before relying
  on subsequent events. A socket can miss an assignment during backgrounding or
  a network outage.
- Keep low-frequency REST polling as a fallback while the user is actively
  waiting for a driver; stop it after assignment, cancellation, delivery, or
  when the screen is disposed.

## Token handling note

The access token is sent as a WebSocket query parameter because browser
WebSocket APIs cannot reliably attach an `Authorization` header during the
handshake. Always use `wss` in production and ensure reverse-proxy access logs
redact the `token` query parameter.
