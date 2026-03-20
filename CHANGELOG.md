# Changelog

All notable changes to **k-tick-mcp** will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Query / Search layer** — `workspace_map`, `query_projects`, `query_folders`, `query_tasks`, `query_notes`, `query_agenda`, and `query_task_history`.
- **Ready-made read views** — `tasks_of_today`, `events_of_today`, `overdue_tasks`, and `stale_tasks`.
- **Operational dashboards/views** — `week_agenda`, `upcoming_tasks`, and `priority_dashboard` for common planning and triage flows.
- **Planning overview** — `week_overview` separates timed events, due tasks, and overdue tasks into a single planning-oriented response.
- **Saved query presets** — `list_query_presets`, `save_query_preset`, `run_query_preset`, and `delete_query_preset` persist reusable filters locally.
- **Verified project/move helpers** — `verified_create_project` and `verified_batch_move` add project existence checks and rollback hints for failed move verification.
- **Verified structural actions** — `create_subtask`, `verified_set_subtask_parent`, `verified_move_tasks`, and `verified_assign_project_folder`.
- **Structured filters** — folder/project scope, tags, priorities, reminders, recurrence, checklist presence, hierarchy shape, and project kind filters.
- **Range-aware agenda access** — date ranges, datetime windows, and HH:MM time windows for scheduled items.
- **Grep-like matching** — substring search, `any` / `all` / `phrase` keyword modes, regex, and exclusion regex across selected fields.
- **Targeted source planning** — the query layer uses scoped `project/{id}/data` reads when filters narrow the search space, instead of defaulting to a full sync.
- **Unit coverage for the query layer** — focused tests for range filters, regex search, note scoping, agenda windows, workspace mapping, and task history.

### Changed

- **Server organization** — shared MCP state/helpers now live in `mcp_api/core.py`, with read/query tools isolated in `mcp_api/read.py`, verified workflow helpers in `mcp_api/verified.py`, and reusable filters/planning in `services/query.py`.
- **Client organization** — the former monolithic `client.py` is now a stable facade over `client_api/transport.py`, `projects.py`, `tasks.py`, `habits.py`, and `stats.py`.

## [0.1.0] — 2025-07-13

### Added

- **46 MCP tools** covering tasks, projects, tags, habits, focus, kanban, folders, subtasks, sync, and user stats.
- **Dual API support** — V1 (official Open API with OAuth2/PAT) and V2 (unofficial web API for extended features).
- **V2 auto-login** — `ticktick-admin session refresh` CLI command for interactive session token renewal.
- **Batch operations** — `batch_create_tasks`, `batch_update_tasks`, `batch_delete_tasks`, `move_tasks`.
- **Kanban management** — `list_columns`, `manage_columns` for board-based workflows.
- **Habit tracking** — full CRUD, check-in, records retrieval, and section listing.
- **Focus / Pomodoro** — `get_focus_stats` for daily focus time analytics.
- **History retrieval** — `get_completed_tasks`, `get_deleted_tasks` with date-range filtering.
- **Helper tools** — `build_recurrence_rule` (RRULE builder), `build_reminder` (trigger builder), `ticktick_guide` (contextual usage guide), `check_v2_availability`.
- **Pydantic v2 models** — `Task`, `Project`, `Habit`, `Tag`, `ChecklistItem`, `SyncResponse`, and more with field validation and coercion.
- **Externalized configuration** — `config.yaml` for API endpoints, timeouts, user-agent, and login paths.
- **`.env` support** — environment variables loaded from `.env` file via `python-dotenv`; `.env.example` with comprehensive auth documentation.
- **Two CLI entry points** — `ticktick-mcp` (MCP stdio server) and `ticktick-admin` (admin/diagnostic CLI via Typer).
- **Test suite** — 135 unit tests (mocked, no network) + 12 live integration scripts (508 assertions against real API).
