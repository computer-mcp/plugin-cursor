---
name: cursor-agent
description: Use this Computer MCP plugin's verified Cursor CLI and ACP session, event, cancellation and interactive-response tools.
---

# Cursor Agent

Discover the host's actual tool names and schemas first. A host prefix may differ from the adapter-native names below. Select the authorized host workspace; the adapter must not invent another working directory or use private Host Services.

Use the projected CLI print command for a single headless task or native model/resume options whose final JSON is sufficient. Read its explicit partial coverage. Do not inject force, trust, sandbox changes or MCP approvals unless the user explicitly requested those native choices. Omit one-way Boolean flags rather than supplying false.

Use `cursor.acp.prompt` for one-shot ACP work. For session reuse or interactive work, call `cursor.acp.session.open`, retain both the adapter `session` and the distinct native `session_id`, then call `cursor.acp.session.prompt.start`. Save the returned `prompt_id`. Read `cursor.acp.events.read` incrementally and `cursor.acp.session.prompt.result` for completion; do not replay the prompt just because a client disconnected.

The default permission policy is reject-once. Choose manual when approvals must be presented. Inspect `cursor.acp.requests.list`; convey the actual question, plan or permission choice to the user and reply with `cursor.acp.requests.respond`, preserving request/option/question IDs. Never infer permission from a human-looking option ID, approve an unoffered choice, or fabricate an answer. Expired requests require inspection, not replay.

`completed: true` is settlement, not necessarily success. Inspect is_error, stop_reason, native_result, truncation and missed-event markers. Use session.cancel to cancel active work and session.close when finished. After adapter replacement, old handles are invalid; use an explicit saved native conversation ID with resume_session_id only when continuation is intended.

Vendor installation, authentication, updates and account setup remain local user operations. Host grants and Cursor permissions are distinct. A working directory is not a sandbox. Protocol fixtures, native initialization and real model execution are different verification claims.
