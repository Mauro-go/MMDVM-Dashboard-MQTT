# MMDVM Dashboard MQTT Multi

Development copy: /opt/MMDVM-Dashboard-MQTT-Multi, branch multi.
The original checkout and running installation are independent.

## Behaviour

- The primary repeater keeps /, /api/* and its existing Admin.
- Added repeaters use /ir3abc/, /ir3abc/api/* and /ir3abc/api/admin/ (also /ir3abc/admin/).
- A callsign selector appears on dashboard and Admin pages.
- /admin/multi/ is protected by the primary Admin session and creates remote repeaters.
- Each added repeater has a fresh Python interpreter and MQTT collector using shared source code.
- Config, SQLite events, MQTT settings, Agent cache, credentials and session secrets are private to each node.
- Cookie names and paths are independent. Primary and sibling logins do not authenticate another node.
- node_id, event topic and Agent prefix are bound at creation and cannot be reassigned by the node Admin.
- Duplicate callsigns, node IDs, event topics, overlapping Agent prefixes and traversal names are rejected.
- Primary wildcard subscriptions exclude traffic belonging to additional nodes.

## Layout

Primary config and data keep their default locations unless explicitly overridden.
For development, use copies inside this checkout, never writable paths into the original installation.

    config/dashboard.ini
    data/main-admin/{admin.json,session-secret}
    data/multi/nodes.json
    data/multi/ir3abc/dashboard.ini
    data/multi/ir3abc/data/{events.sqlite3,mqtt-settings.json,agent-state.json}
    data/multi/ir3abc/admin/{admin.json,session-secret}
    data/multi/ir3abc/{worker.log,collector.log}

All data/ files are excluded from Git. Node directories use 0700 and credential files use 0600.
The event topic must be exact, for example mmdvm/ir3abc/json, without + or #.
The Agent prefix must end with node_id, for example mmdvm-agent/ir3abc.
Legacy MMDVM messages may lack node_id: then the dedicated topic supplies the binding.
A supplied event-level or mode-level node_id must match the node.

## Tests

    python3 -m unittest discover -s tests -v
    python3 -m compileall -q backend
    bash -n scripts/run-multi.sh

Tests create temporary config, credentials and databases.
The broker test uses a separate Mosquitto listener on an ephemeral loopback port;
it never publishes test traffic to production. It is skipped if Mosquitto is unavailable.
Test workers and broker processes are stopped on completion.

## Separate runtime

Prepare an independent runtime (the script refuses existing destination files):

    python3 scripts/prepare-multi.py --source /opt/mmdvm-dashboard-mqtt --state /var/lib/mmdvm-dashboard

This copies config and Admin state, and takes a consistent SQLite backup inside this copy.
Preserve the primary callsign, deployment/node_id, Agent prefix and MQTT settings.
Use sqlite3.Connection.backup for a live database, rather than copying its database file directly.
Do not point development path variables into the original installation.

    bash scripts/run-multi.sh

The backend listens only on 127.0.0.1:8090, leaving the existing backend on 8089 intact.
Run the primary mqtt_collector.py separately with the same MMDVM_NODE_CONFIG, MMDVM_NODE_DATA and MMDVM_DASHBOARD_STATE_DIR variables.
Additional collectors are supervised by their workers.
Use a service manager for production, keeping children in the same service control group.
Existing primary Telegram services are unchanged; Multi does not start per-node Telegram bot processes.

## HTTPS / Apache

The existing install.sh and install.sh.bak are single-dashboard installers.
Do not run them to deploy this copy: they target the existing installation and only proxy /api/.
Multi needs a dedicated HTTPS VirtualHost that proxies the entire path tree to its backend.
See scripts/multi-apache-vhost.conf.example. Replace hostname/certificate paths and run apachectl configtest before deployment.
Do not add a global ProxyPass /, which would affect other sites.
The primary page must also use the Multi backend so its callsign selector is rendered.
Admin cookies remain Secure, HttpOnly and SameSite=Strict. Use HTTPS for login and node creation.

## Scope

Added nodes are remote MQTT repeaters. The primary can keep its local or remote configuration.
Node creation, recoverable deletion and restoration are implemented; editing node identities and renaming URLs are outside this version.
Each node owns its event database instead of partitioning a shared table by node_id.
Workers serialize requests within a node; different nodes run independently.

## Delete and restore

In /admin/multi/, Elimina asks for confirmation, stops the node worker and collector,
removes its URL/menu entry and moves its private directory into data/multi/.trash/<archive_id>.
The primary repeater has no delete action. Only the primary Admin may delete or restore nodes;
both operations require CSRF and same-origin checks.
Deleted records are retained in nodes.json with archive_id and deleted_at.
The Ripetitori eliminati section restores data, MQTT settings, credentials and the original URL.
Restore refuses conflicts with an active callsign, node_id, topic or Agent prefix.
Archived MQTT traffic remains excluded from the primary wildcard collector.
No permanent purge is performed. A committed deletion interrupted before its directory move
is completed when the Multi backend next starts.
