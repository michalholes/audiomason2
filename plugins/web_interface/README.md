# web_interface (standalone)

Standalone web UI server for AudioMason (server-driven UI, variant B).

This plugin runs its **own** FastAPI/uvicorn server and does **not** depend on the legacy `web_server` plugin.

## Run

From repo root:

```bash
python3 plugins/web_interface/run.py --host 0.0.0.0 --port 8081
```

Environment alternatives:

- `WEB_INTERFACE_HOST` (default `0.0.0.0`)
- `WEB_INTERFACE_PORT` (default `8081`)

Optional:

- `WEB_INTERFACE_LOG_PATH=/path/to/logfile` (enables `/api/logs/*`)
- `WEB_INTERFACE_CONFIG_PATH=/path/to/config.json` (enables `/api/config` read/write)
- `WEB_INTERFACE_UI_CONFIG=/path/to/ui.json` (overrides UI pages/nav)

## Open

- UI: `http://localhost:8081/ui/`

## Sanity checks

- `http://localhost:8081/api/health`
- `http://localhost:8081/api/ui/nav`
- `http://localhost:8081/api/ui/page/dashboard`
- `http://localhost:8081/api/status`
