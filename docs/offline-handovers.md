# Driver handover API contract

The driver app owns the offline queue. The server has no offline sync worker or
special replay endpoint. Retry each POST with the **same** UUID and payload after
a timeout, and refresh the normal package detail or current assignment response
to learn the authoritative status. Local code verification may finish the
doorstep interaction, but only a successful server response confirms the
package transition.

## Route snapshot

`GET /api/transporters/current-assignment/` includes `assignment_id`,
`pickup_code_verifier`, `dropoff_code_verifier`, and `payment` on an active
assignment, even when it began on a previous day. `payment` contains `is_paid`,
`is_pay_forward`, `amount`, and `cash_due_stage` (`pickup`, `dropoff`, or `null`).
The verifier has `version: 1`, `algorithm: "pbkdf2_sha256"`,
`iterations: 600000`, and Base64 `salt` and `digest`. Hash the six ASCII digits
exactly as entered, including a leading zero. The snapshot has no fixed time
expiry; a later server state change can still reject the handover.

Fixed test vector: code `012345`, salt bytes
`000102030405060708090a0b0c0d0e0f`, digest Base64
`UTlLVv5gSoMgRDHVh6jC2Zxc1zX/hZV7edf76/tYV0M=`.

## POD upload

`POST /api/intracity/package-images/{package_id}/` uses multipart fields
`image`, `upload_id` (UUID), `assignment_id` (UUID), and `stage` (`pickup` or
`dropoff`). It returns an `id` for the image. An identical retry returns that
record with HTTP 200; a new upload returns 201. Reusing `upload_id` with
different bytes or metadata returns 409. The file is stored as uploaded.
`GET` on the same route lists package images. The original generic image POST
remains available during the driver app rollout.

## Pickup and dropoff

Use the existing `POST /api/transporters/pickup-package/` with `sender_code`,
or `POST /api/transporters/dropoff-package/` with `receiver_code`. New app
requests also send `package_id`, `request_id` (UUID), `assignment_id` (UUID),
and `cash_received` (boolean). `image_id` is required for pickup POD, and is
optional for dropoff. `captured_at` is optional and is audit metadata, not
proof of when the handover occurred. For offline identity fields, `request_id`
and `assignment_id` are required together. A cash handover sends
`cash_received: true` in this POST; the app does not first call
`confirm-cash-received/`.

The server verifies the code, photo ownership, assignment, stage, and invoice.
It commits cash and the package transition together. A successful retry with
the same `request_id` and payload returns the recorded 200 response without
repeating side effects. Reusing that ID with different data returns 409.
A valid-code request that conflicts with current server state returns 409 and
enters staff review; its response includes `request_id` and
`review_status: "pending"`. Retrying after staff resolution returns the final
accepted response or `review_status: "rejected"`. Staff can inspect cases through
`GET /api/adminportal/handover-reviews/` and resolve one through
`POST /api/adminportal/handover-reviews/{request_id}/resolve/` with `action`
(`accept` or `reject`) and a required `reason`. Acceptance never overrides a
cancelled package or another driver's assignment.

Upload a pickup image, then submit pickup. Dropoff does not require a POD image.
Keep the photo binary and request UUIDs in the client queue until the server
confirms or staff resolves the attempt. The queue must also retain the entered
six digit code securely until sync so the server can verify it independently;
the local verifier result cannot replace the code in the POST. Encrypt that
queued code on the device, avoid logging it, and delete it after reconciliation.
Existing driver calls without POD fields remain valid during rollout.
