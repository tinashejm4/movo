# WebSocket Assignment Notifications

Real-time package assignment notifications via WebSocket for the Movo API.

## Overview

The WebSocket service broadcasts package assignments to connected clients in real-time. Two connection modes are supported:

- **Global**: Receive all package assignments across the system
- **Package-specific**: Receive assignments for a single package only

## Connection URLs

### Global Assignments (All Packages)
Citi-style evidence pack: 
Connect to receive all package assignments in real-time:

```
ws://localhost:8000/ws/intracity/assignments/
```

or without trailing slash:

```
ws://localhost:8000/ws/intracity/assignments
```

### Per-Package Assignments

Connect to receive assignments for a specific package by ID:

```
ws://localhost:8000/ws/intracity/assignments/<package_id>/
ws://localhost:8000/ws/intracity/assignments/<package_id>
```

Replace `<package_id>` with the numeric package ID.

**Example:**
```
ws://localhost:8000/ws/intracity/assignments/42/
```

## Messages

### Connection Acknowledgement

Upon successful connection, the server sends a connection confirmation:

```json
{
  "event": "connected",
  "data": {
    "group": "package_assignments",
    "package_id": null,
    "subscribed": true
  }
}
```

**Fields:**
- `group`: The subscription group (either `package_assignments` or `package_<id>`)
- `package_id`: The package ID if connected to a per-package stream, `null` for global
- `subscribed`: Boolean indicating successful group subscription

### Package Assignment Event

When a package is assigned to a biker, this event is broadcast:

```json
{
  "event": "package_assigned",
  "data": {
    "package_id": 1,
    "slug": "PKG-2025-001",
    "is_fast_delivery": false,
    "biker_id": 5,
    "biker_name": "John Doe",
    "biker_phone": "0771234567",
    "assigned_at": "2025-07-29T10:30:45.123456+02:00",
    "added_at": "2025-07-29T09:15:30.654321+02:00"
  }
}
```

**Fields:**
- `package_id`: Unique package identifier
- `slug`: Human-readable package reference
- `is_fast_delivery`: Whether this is a fast delivery package
- `biker_id`: Assigned biker's ID
- `biker_name`: Assigned biker's full name
- `biker_phone`: Assigned biker's phone number
- `assigned_at`: ISO 8601 timestamp of assignment
- `added_at`: ISO 8601 timestamp of package creation

## Usage Examples

### JavaScript/Browser

#### Global Assignments

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/intracity/assignments/");

ws.onopen = () => {
  console.log("Connected to global assignments stream");
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.event === "connected") {
    console.log("Subscription confirmed:", message.data.group);
  } else if (message.event === "package_assigned") {
    const assignment = message.data;
    console.log(`Package ${assignment.package_id} assigned to ${assignment.biker_name}`);
    // Update UI with new assignment
  }
};

ws.onerror = (error) => {
  console.error("WebSocket error:", error);
};

ws.onclose = () => {
  console.log("Disconnected from assignments stream");
};
```

#### Per-Package Assignment

```javascript
const packageId = 42;
const ws = new WebSocket(`ws://localhost:8000/ws/intracity/assignments/${packageId}/`);

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.event === "package_assigned") {
    const { biker_name, biker_phone, assigned_at } = message.data;
    console.log(`Your package has been assigned to ${biker_name}`);
    console.log(`Biker phone: ${biker_phone}`);
    console.log(`Assigned at: ${assigned_at}`);
  }
};
```

### React Example

```jsx
import { useEffect, useState } from "react";

export function AssignmentNotifications({ packageId }) {
  const [assignment, setAssignment] = useState(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const wsUrl = packageId
      ? `ws://localhost:8000/ws/intracity/assignments/${packageId}/`
      : `ws://localhost:8000/ws/intracity/assignments/`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);

      if (message.event === "package_assigned") {
        setAssignment(message.data);
      }
    };

    return () => ws.close();
  }, [packageId]);

  if (!connected) return <p>Connecting...</p>;
  if (!assignment) return <p>Waiting for assignment...</p>;

  return (
    <div>
      <h3>Package Assigned!</h3>
      <p><strong>Biker:</strong> {assignment.biker_name}</p>
      <p><strong>Phone:</strong> {assignment.biker_phone}</p>
      <p><strong>Package:</strong> {assignment.slug}</p>
    </div>
  );
}
```

## API Integration

### Triggering Assignments

Call the REST API endpoint to trigger batch assignment of pending packages:

```
POST /api/intracity/assign-pending-packages/
```

**Request:**
```json
{}
```

**Response:**
```json
{
  "message": "Pending packages assigned successfully",
  "assigned_count": 3,
  "unassigned_count": 0,
  "assigned_packages": [
    {
      "package_id": 1,
      "slug": "PKG-2025-001",
      "is_fast_delivery": false,
      "biker_id": 5,
      "biker_name": "John Doe",
      "biker_phone": "0771234567",
      "assigned_at": "2025-07-29T10:30:45.123456+02:00",
      "added_at": "2025-07-29T09:15:30.654321+02:00"
    }
  ]
}
```

Connected WebSocket clients will receive `package_assigned` events simultaneously for each assignment.

## Connection Behavior

### Global vs Per-Package

- **Global socket receives:**
  - All assignments broadcast by the system
  - Suitable for dashboards, monitoring, admin panels

- **Per-package socket receives:**
  - Only assignments for that specific package
  - Suitable for customer tracking, package-level notifications
  - Two different packages on different sockets receive independent streams

### Subscription Isolation

When connected to a per-package URL (e.g., `/ws/intracity/assignments/42/`), the connection subscribes only to that package's assignment group. Global assignments to other packages are **not** received.

This prevents notification noise and improves privacy for per-package customer-facing applications.

## Error Handling

### Connection Failures

```javascript
ws.onerror = (error) => {
  // Common causes:
  // 1. Redis timeout (temporary, server auto-retries)
  // 2. Invalid package_id (404 on HTTP GET, not websocket upgrade)
  // 3. Network connectivity issues
};

ws.onclose = () => {
  // Implement reconnection logic with exponential backoff
  setTimeout(() => {
    // Attempt reconnect
  }, 1000);
};
```

### Transient Redis Failures

The server is configured to retry Redis operations with a 15-second timeout. Brief Redis stalls will not immediately disconnect clients; however, events may be delayed or lost during extended outages.

For production, consider:
- Monitoring Redis health via `/api/health/`
- Implementing client-side reconnection with backoff
- Using both WebSocket and polling as a fallback

## Configuration

### Environment Variables (Backend)

### Single-Server Deployment

This uses Django Channels' in-memory backend instead of Redis, suitable only for non-distributed deployments.

## Testing

### Manual Testing with Browser DevTools

```javascript
// Global assignments
const ws = new WebSocket("ws://localhost:8000/ws/intracity/assignments/");
ws.onmessage = (e) => console.log(JSON.parse(e.data));

// Per-package (replace 1 with a real package ID)
const ws2 = new WebSocket("ws://localhost:8000/ws/intracity/assignments/1/");
ws2.onmessage = (e) => console.log(JSON.parse(e.data));

// Trigger assignments via API
fetch("http://localhost:8000/api/intracity/assign-pending-packages/", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_TOKEN"
  },
  body: "{}"
}).then(r => r.json()).then(console.log);
```

### Using wscat (Terminal)

```bash
npm install -g wscat

# Global assignments
wscat -c ws://localhost:8000/ws/intracity/assignments/

# Per-package
wscat -c ws://localhost:8000/ws/intracity/assignments/1/
```

## Performance Notes

- Each WebSocket connection consumes minimal server resources (async I/O)
- Redis pubsub scales horizontally across multiple backend instances
- Per-package subscriptions naturally partition load by reducing message fan-out
- No polling required; events are push-based and low-latency

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Connection 404 | HTTP GET to ws path instead of upgrade | Use correct ws:// scheme, not http:// |
| Timeout after 2 seconds | Redis unreachable | Verify Redis health: `docker compose ps redis` |
| Messages not received | Using HTTP server instead of ASGI | Ensure backend uses Daphne ASGI server |
| All packages on per-package socket | Subscription mismatch | Verify correct package_id in URL |
| Serialization error in logs | Invalid data type in payload | Contact support; server should handle safely |

