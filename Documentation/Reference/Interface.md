# Interface contract

## Native and host contracts

The tested native version is recorded in `cli-tree.json`. Both projected CLI calls and new ACP sessions require its exact version assertion. Changing the supported native baseline requires a reviewed plugin update; a version match is not proof of authentication or model availability.

The CLI contribution preserves the declared argv order, optional native flags and an explicit `--` before the prompt. It returns native JSON through the host execution envelope. It does not load interactive help at runtime or claim complete upstream coverage. Explicit `force`, `trust`, `approve_mcps` and sandbox overrides are vendor choices, never defaults injected by the adapter or host.

The MCP adapter implements standard newline-delimited JSON-RPC over stdio, with MCP initialization, tools/list, tools/call, ping and cancellation notifications. Supported MCP dates are 2024-11-05, 2025-03-26 and 2025-06-18. An unsupported proposed date receives the adapter's supported date rather than an unimplemented echo. Tool results use `structuredContent.result`; tool failures set `isError` and include an error code. Protocol errors remain JSON-RPC errors. Tool schemas are the callable source of truth.

## Tools

| Native MCP tool | Behavior |
| --- | --- |
| `cursor.acp.prompt` | One-shot ACP open, prompt and confirmed cleanup |
| `cursor.acp.session.open` | Create an adapter handle and native session, or load an explicit native conversation |
| `cursor.acp.session.prompt` | Submit one prompt and wait for its bounded result |
| `cursor.acp.session.prompt.start` | Return immediately with a background `prompt_id` |
| `cursor.acp.session.prompt.result` | Inspect the latest identified background prompt |
| `cursor.acp.session.list` | List sessions owned by this adapter instance |
| `cursor.acp.session.mode` | Select a mode actually advertised by the current native session |
| `cursor.acp.session.cancel` | Request native cancellation; unresolved cancellation retires the session |
| `cursor.acp.session.close` | Retire only this adapter-owned process and session handle |
| `cursor.acp.events.read` | Read a bounded page using absolute cursors |
| `cursor.acp.requests.list` | Read blocking native permission, question or plan requests |
| `cursor.acp.requests.respond` | Resolve exactly one active request with a validated native response |

These are adapter-native names. Computer MCP can apply a host-selected prefix. Discover the actual exposed names rather than assuming a projection spelling.

An adapter `session` handle is not a native `session_id`. Handles, pending request IDs and background results are in-memory and scoped to one adapter process. A reconnect that starts a new adapter cannot adopt old handles. To resume after replacement, open with an explicit saved native `resume_session_id`. Closing a handle does not delete the native saved conversation. At most eight sessions are retained. Each session admits one prompt or control RPC at a time; independent sessions can proceed concurrently. Only the latest background prompt result is retained per session.

## Interactive workflow

Use `session.open` with `permission_policy: manual`, then `session.prompt.start`. Poll `requests.list` and `events.read`, respond to the offered request, then poll `session.prompt.result`. This avoids holding a northbound call open while waiting for a human. A synchronous prompt also processes requests, but its caller must provide another concurrent call for the reply.

The default permission policy is `reject-once`. Explicit `allow-once`/`allow-always` select an offered option by its ACP kind, preserving the opaque `optionId`; if the requested allow kind is absent, reject or cancel instead. Manual decisions accept only a currently offered option. Questions and plans are never auto-answered. The reply envelope is the native Cursor `outcome` object, for example:

```json
{"session":"ADAPTER_HANDLE","request_id":"PENDING_REQUEST","response":{"outcome":{"outcome":"selected","optionId":"EXACT_OFFERED_OPTION"}}}
```

Question answers must use the offered question and option IDs and obey single/multiple selection. Plans accept `accepted`, `rejected` or `cancelled` and their documented optional fields. Duplicate, stale and unoffered replies fail. Unknown vendor requests receive method-not-found, not fabricated success.

## Bounds, cancellation and failures

An ACP frame is bounded to 1 MiB before waiting for a newline. Event retention is bounded by both 256 events and 256 KiB. Text accumulation is bounded to 128 KiB; omissions/truncation are reported. Pages use absolute cursors, `next_cursor`, `has_more` and `missed_events`. An event larger than the requested page becomes explicit omission metadata so pagination can progress. Responses retain the bounded native prompt result; absent stopReason is an error, and native cancellation is not successful task completion.

Prompts default to 300 seconds and accept up to 1800 seconds. Session setup defaults to 45 seconds. Transport startup and cleanup can add bounded latency. Pending requests expire with their native operation. Cancellation sends ACP session/cancel, waits for native settlement, and retires the owned process if it cannot settle within its grace period. A cancelled background request is not automatically replayed. Cancelling the start call after it returned does not identify the background task: use the returned session/prompt handle.

The private supervisor observes adapter EOF/termination and owns the vendor process group. It retains the leader until termination and reaping, then sends a separate bounded cleanup acknowledgement. Missing acknowledgement is `cleanup_unconfirmed`, never a clean success inferred from exit alone. Escaped, independently reparented processes are not claimed as owned. Host callback descriptors/COMPUTER_MCP metadata are not forwarded to the vendor. The process working directory is not an OS sandbox.

Representative errors include invalid_arguments, unknown_session, busy, incompatible_vendor, vendor_failed, invalid_vendor_response, frame_too_large, result_too_large, timeout, cancelled and cleanup_unconfirmed. Failed/unknown writes are not automatically retried. Native output may contain sensitive user content; callers must handle it accordingly.

## Sources

- https://cursor.com/docs/cli/acp
- https://cursor.com/docs/cli/reference/parameters
- The installed native `agent --help`, `agent --version` and `agent acp --help` used to maintain the pinned CLI tree.

Vendor protocol observations, fixture tests, host interoperability and authenticated backend execution are separate evidence classes.
