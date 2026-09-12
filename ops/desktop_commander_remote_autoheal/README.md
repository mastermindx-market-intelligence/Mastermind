# Desktop Commander Remote MCP auto-heal

Supervises the Remote MCP CLI process on macOS; this is unrelated to the Desktop Commander GUI app.

The launchd wrapper reuses the existing Desktop Commander device/session store, persists token rotations there, never replays user commands, restarts after SIGTERM or local MCP failure, and backs off indefinitely rather than permanently exhausting after repeated crashes.

When an unmanaged manual bridge already exists, the supervisor stays in `waiting_for_incumbent` and starts no second remote bridge. It takes over only after that incumbent disappears.

Vendor baseline is Desktop Commander 0.2.50, which also includes upstream proactive local-MCP recovery for the outer-online/inner-disconnected failure mode.

Production proof requires a real managed generation plus a small remote file read and short remote process execution. Installation or fixture tests alone are not `PROVEN_LIVE`.
