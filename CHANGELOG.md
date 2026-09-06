# Changelog

All notable changes to the WhatsApp Automation Tool will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-09-06

Big correctness, security and CI pass.

### Added
- **The web dashboard now actually runs campaigns** - `/api/campaign/start` sends
  in a background thread with a live progress bar, a "Dry run" toggle, and a
  `/api/campaign/progress` endpoint
- Per-lead result records on `CampaignResult`; `--output` writes them to a CSV
- `--verbose` now raises the log level to DEBUG (it was parsed and ignored)
- Message send retries on failure (`max_retries` / `retry_delay`, configurable)
- **CSRF guard** on the web UI: state-changing requests need a JSON body or a
  same-origin `Origin`/`Referer`; `SameSite=Lax` session cookie
- CI rewritten: `lint` / `test` (3.11 + 3.12) / `smoke` / `docker` / `security`.
  `smoke` boots a live web server and drives the full campaign workflow over HTTP
  (`scripts/healthcheck.py`); `docker` builds the image, runs `pytest` inside it,
  boots the container and health-checks the web UI + noVNC
- Test coverage for `whatsapp_automation`, `config`, `main`, web UI API and
  template error paths (13 → 51 tests, ~90% on `src/` + `config/`)
- `WA_DEBUG` / `PORT` env vars for the web UI
- `.dockerignore`, `.gitattributes` (LF for shell scripts / Dockerfile)
- README screenshot; OCI image labels; `docs/social-preview.png`

### Changed
- Config file **and** `WHATSAPP_*` / `LOG_*` env vars are now actually applied
  (previously the loaded config was passed as a nested dict and silently ignored)
- **`pywhatkit` moved out of the core `requirements.txt`** into `requirements-send.txt`
  (it dragged in Flask/wikipedia/pyautogui/Pillow). CI, tests and the web UI no
  longer install it; the Docker image does. `pip install ".[send]"` for local sends.
- **Docker entrypoint only starts the GUI stack (Xvfb/chromium/noVNC) for `serve`** -
  `docker run <img> python main.py ...` now runs straight through. The web UI runs
  in the foreground so `command: sleep infinity` is no longer needed.
- `docker-compose.yml` trimmed: dropped the obsolete `version:`, the unused `redis`
  service, and dead env vars
- Web UI `debug` mode is **off** by default (Werkzeug debugger is an RCE risk)
- Docker image no longer ships dev/docs tooling (black, mypy, sphinx);
  `apt --no-install-recommends`, fewer packages
- `web_ui/requirements.txt` layers on the core requirements instead of re-pinning
- `publish-ghcr.yml` publishes on version tags **and** `main`, re-tags `:latest`
  on release, bumped to `build-push-action@v6` with GHA cache
- `pyproject.toml` version is static (the dynamic `attr` path was invalid);
  added `[send]` and `[web]` extras
- README rewritten around the real feature set and a copy-paste quick start

### Fixed
- **Path traversal** - the template-create endpoint built a path from the raw
  `language` / `category` fields; now validated and confined to `templates/`
- `/api/templates` returned display-name strings, so every card in the dashboard
  template grid rendered as "undefined"
- Inter-message delay compared a pandas index label to a positional index (wrong
  on a sliced CSV)
- Malformed / non-mapping template files are skipped or rejected cleanly instead
  of poisoning the template store
- Web UI loaded **zero** message templates when run from `web_ui/` (path collision
  with Flask's own `templates/` dir)
- Campaign flow in the dashboard never called `select-template` / `confirm`, so
  "start" always failed
- Stale unit tests referencing removed `business_proposal` templates
- CI: deprecated `actions/*@v3`, Docker Hub push with missing secrets, mypy failing
  on modern numpy stubs, source never actually run through black/isort, `:latest`
  never re-tagged on release
- `--list-templates` crashing on non-UTF-8 consoles (Windows cp1252)
- `.pre-commit-config.yaml` used the removed `types-all` package

## [1.0.0] - 2024-04-23

### Added
- Initial release of WhatsApp Automation Tool
- WhatsApp Web automation via pywhatkit
- CSV lead list processing with pandas
- Phone number validation with phonenumbers
- Message template system with variable substitution
- CLI interface with argparse
- Docker support with noVNC GUI (Linux VM only)
- Rate limiting for message sending
- Dry-run mode for testing
- Progress tracking with tqdm
- Configuration management with YAML
- Logging system
- Test suite with pytest
- GitHub Actions CI/CD workflows
- GitHub Container Registry (GHCR) publishing
