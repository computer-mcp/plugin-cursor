# Interface contract

## Native and host contracts

The tested native version is recorded in `cli-tree.json`. Both projected CLI calls and new ACP sessions require its exact version assertion. Changing the supported native baseline requires a reviewed plugin update; a version match is not proof of authentication or model availability.

The CLI contribution preserves the declared argv order, optional native flags and an explicit `--` before the prompt. It returns native JSON through the host execution envelope. It does not load interactive help at runtime or claim complete upstream coverage. Explicit `force`, `trust`, `approve_mcps` and sandbox overrides are vendor choices, never defaults injected by the adapter or host.

The MCP adapter implements standard newline-delimited JSON-RPC over stdio, with MCP initialization, tools/list, tools/call, ping and cancellation notifications. Supported MCP dates are 2024-11-05, 2025-03-26 and 2025-06-18. An unsupported proposed date receives the adapter's supported date rather than an unimplemented echo. Tool results use `structuredContent.result`; tool failures set `isError` and include an error code. Protocol errors remain JSON-RPC errors. Tool schemas are the callable source of truth.

## Reviewed provider and caller permissions

The manifest requests provider Project write to open Cursor sessions and run requested
project tasks in owner-selected worktrees. MCP callers need Project write by default.
Exactly `cursor.acp.session.prompt.result`, `cursor.acp.session.list`,
`cursor.acp.events.read` and `cursor.acp.requests.list` require Project read.
These complete per-tool overrides replace the manifest default; host effect requirements
remain additive. Cancellation, close, mode and native-response delivery require write.
Both caller authority and provider authority must admit the effect. Plugin use alone
does not authorize project execution. Runtime metadata never sets caller requirements.
CLI invocation retains Project write plus Plugin use; Skills consumption retains Skills
plus Plugin use. Shipping a skill does not request provider Skills authority.

The sandbox requests a custom network ceiling of `api2.cursor.sh` for Cursor
API requests and `api5.cursor.sh` for agent requests. The owner reviews that
ceiling at enablement and must approve updates that widen it. The owner may
narrow the selection, and Host policy limits effective access. Trusted
hosts are excluded and Full access defaults to off.
[Cursor ACP](https://cursor.com/docs/cli/acp) and
[Cursor network configuration](https://cursor.com/docs/enterprise/network-configuration#ip-allowlisting)

The installed provider uses host-provisioned persistent container paths for
HOME, cache and state. Temporary storage is execution-local. See the
[installation guide](Installation.md#dependencies-and-configuration) for sign-in
requirements.

The host selects the worktree, protects unrelated projects, host data and
other containers, and retires writers before removal. This adapter does not
request `projects-v1` or perform host lifecycle calls.

## Host risk metadata

Every MCP tool declares `_meta["io.github.computer-mcp/risk"]`. Model execution
and continuation declare `full-shell`: native permission defaults are not a
host-enforced sandbox. Catalog, result, event and pending-request inspection
declare `read-only`. Cancellation and owned-process retirement declare
`destructive`. The host applies these as minimum classifications, intersects
its own grants, and retains approval authority. Standard MCP annotations remain
hints rather than permissions.

Session open/load, mode changes and interactive responses also declare
`full-shell`; they can initialize native tools or continue executable work.

## Runtime work resource

The adapter advertises ordinary MCP resources and the version-1 declaration in
`_meta["io.github.computer-mcp/work"]` on its tool definitions. `resources/list`
lists `computer-mcp://runtime/work/v1`; `resources/read` returns one JSON text
content entry. The report has `format_version`, a connection-local UUID
`instance_id`, a nonnegative exact integer `revision`, and the complete
`resources` array. Unchanged resource sets keep their revision; changed sets
advance it. At most 1,024 resources and 512 KiB of report text are allowed.

Each live resource has kind `cursor.session`, the adapter `session` handle as
`id`, the opening call's host-supplied
`_meta["io.github.computer-mcp/work-invocation"]` UUID as `acquired_by`, and
state `active` or `uncertain`. This reference binds lifecycle observation; it
grants no authority and is not a native session ID. It is never read from tool
arguments or forwarded to the vendor process.

A session is owned from pending startup through idle periods, repeated or
background prompts and interactive requests. Completing a prompt does not close
its session. Removal requires confirmed process cleanup, settled startup and
completion of the owned background thread. Closing with unconfirmed cleanup
reports `uncertain` and keeps the session against capacity. A one-shot prompt
releases its session after the same cleanup boundary. No report can substitute
for permission, native execution success or authenticated model evidence.

Ordinary clients may continue to call tools without work-invocation metadata.
If such a client creates a live session, the work resource returns unavailable
evidence until unbound work is released; it never reports a falsely empty
snapshot. Malformed invocation metadata is rejected before execution. Report
reads do not launch a vendor, terminate a session, change permissions or replay
work. The adapter does not require resource subscriptions; hosts may poll.

See the host's [provider work contract](https://github.com/computer-mcp/computer-mcp/blob/master/Documentation/Reference/MCPProtocol.md#downstream-provider-work)
for acquisition expiry, snapshot validation and host-side uncertainty.

## Vendor execution

Computer MCP runs the registered ACP contribution using the reviewed
`cursor-vendor-execution.json` signature. It selects the `cursor-agent`
dependency, verifies the version probe, and owns the separate probe and
workload children for each acquisition. The adapter negotiates the private
vendor channel before advertising managed execution. Managed startup requires
that channel and does not fall back to launching a local child. Standalone
stdio clients use the local supervisor and select the executable through
`--executable`, `CURSOR_AGENT_EXECUTABLE`, or PATH.

The adapter initializes ACP and calls `authenticate` with the advertised
`cursor_login` method before creating or loading a session. An authentication
RPC rejection stops setup. The adapter reports `authentication_required` for
ACP Authentication Required (`-32000`) and `vendor_error` for other
authentication rejections. Both include the numeric RPC code and omit the
vendor message and data. Only `authentication_required` includes a sign-in
hint appropriate to installed or standalone use. [Cursor ACP](https://cursor.com/docs/cli/acp) ·
[ACP error codes](https://agentclientprotocol.com/protocol/v1/schema#errorcode)

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

Question answers must use the offered question and option IDs and obey single/multiple selection. Plans accept `accepted`, `rejected` or `cancelled` and their documented optional fields. Duplicate, stale and unoffered replies fail. Each request is bound to its active native operation and session; response delivery and operation retirement are serialized. Unknown vendor requests receive method-not-found, not fabricated success.

A definitive Host refusal before writing returns `response_refused`. The active
turn retains ownership of its pending request through stop or completion.
Unknown delivery returns `response_unknown` and retires the affected session
without replaying the answer.

## Bounds, cancellation and failures

An ACP frame is bounded to 1 MiB before waiting for a newline. Event retention is bounded by both 256 events and 256 KiB. Text accumulation and its serialized JSON value are each bounded to 128 KiB; omissions/truncation are reported. Pages use absolute cursors, `next_cursor`, `has_more` and `missed_events`. An event larger than the requested page becomes explicit omission metadata so pagination can progress. Responses retain the bounded native prompt result; absent stopReason is an error, and native cancellation is not successful task completion.

Prompts default to 300 seconds and accept up to 1800 seconds. Session setup defaults to 45 seconds. Transport startup and cleanup can add bounded latency. Pending requests expire with their native operation. Cancellation of a dispatched prompt sends ACP `session/cancel` once and waits up to two seconds for the correlated reply. The adapter preserves a native cancellation, a completion that won the race, or a native error. A settled cancellation or completion permits session reuse. A correlated managed prompt error also leaves the session available. If managed cancellation cannot settle within the grace period, the adapter retires the affected session and reports `cancellation_unsettled`. A cancelled background request is not automatically replayed. To cancel background work after the start call returns, select its session handle.

For managed execution, the Host supplies cleanup receipts for both child phases.
An unconfirmed start is reconciled against its existing reservation. Standalone
execution uses a private supervisor that observes adapter EOF or termination.
It retains the process group leader until termination and reaping, then sends
a separate cleanup acknowledgment. A session with unconfirmed cleanup remains
charged against capacity. Vendor processes receive neither the private channel
nor reserved Host environment metadata. The working directory alone provides
no sandbox enforcement.

Representative errors include invalid_arguments, unknown_session, busy, incompatible_vendor, vendor_failed, invalid_vendor_response, frame_too_large, result_too_large, timeout, cancelled and cleanup_unconfirmed. Failed/unknown writes are not automatically retried. Native output may contain sensitive user content; callers must handle it accordingly.

## Sources

- https://cursor.com/docs/cli/acp
- https://cursor.com/docs/cli/reference/parameters
- The installed native `agent --help`, `agent --version` and `agent acp --help` used to maintain the pinned CLI tree.

Vendor protocol observations, fixture tests, host interoperability and authenticated backend execution are separate evidence classes.

## Continuation binding

Tools that accept an existing adapter handle declare
`_meta["io.github.computer-mcp/continuation"]` with format version 1. The selector
matches kind `cursor.session` and primary resource `id` against argument
`session` using JSON Pointer `/session`. This identifies the actual
connection-owned lifetime; it does not rebind acquisition or grant permissions.
New work and unscoped listings do not claim an existing owner. The declaration
uses ordinary MCP metadata and requires no private Host Services. Hosts validate
and retain it on its originating connection; gateway reexports strip it. Runtime
generation selection remains host-owned, and this declaration alone does not
enable live configuration changes.
