# Product 0.6.1 Workbench failure scenarios

These scenarios are tracked separately from the successful four-slide corpus so
that a release report can attribute failures to the correct boundary.

- `CONFLICT`: modify the source on disk after session load, then Save with the
  session's base SHA. The external bytes remain unchanged and the draft remains
  available for reconciliation.
- `recovery`: stop a session with a dirty draft, reopen the same source, and
  explicitly restore the separate recovery record. Restore never auto-saves.
- `loopback`: startup binds to `127.0.0.1`; the command does not advertise or
  accept a LAN/remote Workbench endpoint.
- `session token`: API reads require the unguessable token; mutations also
  require the current same-session ID.
- `authorized asset root`: Preview local resources resolve below the source
  directory; traversal and executable HTML/JavaScript resources are blocked.
- `public network`: Preview rewrites/blocks remote resources and uses a
  restrictive frame policy; the browser page has no CDN or runtime npm input.
