"""
Shared MCP server core: FastMCP instance, catalog, and common helpers.
"""
from __future__ import annotations

from typing import Any, Optional, TypeAlias

from mcp.server.fastmcp import FastMCP

from ..config import SERVER_NAME, STATE_DIRECTORY, has_v2_auth, ENV_SESSION_TOKEN, SESSION_COOKIE_NAME
from .. import client
from ..models import TickTickAPIError, Priority, build_reminder_trigger, build_rrule
from ..services.query_presets import QueryPresetStore
from ..services.query import TaskFilterSpec, TickTickQueryService

mcp = FastMCP(SERVER_NAME)

StrListArg: TypeAlias = Optional[list[str] | str]

TOOL_CATALOG = {
    "📋 Projects (V1)": {
        "tools": ["list_projects", "get_project_detail", "create_project", "update_project", "delete_project"],
        "desc": "CRUD operations on TickTick projects/lists.",
    },
    "✅ Tasks — Read (V1)": {
        "tools": ["get_inbox", "get_project_tasks", "get_task_detail"],
        "desc": "Fetch tasks from inbox or specific projects.",
    },
    "🔎 Query & Search": {
        "tools": [
            "workspace_map",
            "query_projects",
            "query_folders",
            "query_tasks",
            "query_notes",
            "query_agenda",
            "query_task_history",
            "tasks_of_today",
            "events_of_today",
            "week_agenda",
            "week_overview",
            "upcoming_tasks",
            "overdue_tasks",
            "stale_tasks",
            "priority_dashboard",
            "list_query_presets",
            "save_query_preset",
            "run_query_preset",
            "delete_query_preset",
        ],
        "desc": "Fine-grained exploration: folders, projects, notes, agenda windows, regex and structured task filters.",
    },
    "✏️ Tasks — Write (V1)": {
        "tools": ["create_task", "update_task", "complete_task", "reopen_task", "delete_task"],
        "desc": "Create, modify, complete, reopen or delete tasks.",
    },
    "⚡ Tasks — Batch (V2)": {
        "tools": ["batch_create_tasks", "batch_update_tasks", "batch_delete_tasks", "move_tasks", "set_subtask_parent"],
        "desc": "Bulk task operations: create/update/delete many at once, move between projects, set parent-child.",
    },
    "🛡️ Verified Actions": {
        "tools": [
            "create_subtask",
            "verified_create_project",
            "verified_set_subtask_parent",
            "verified_move_tasks",
            "verified_batch_move",
            "verified_assign_project_folder",
        ],
        "desc": "Safe wrappers that execute structural TickTick actions and re-read state to verify the outcome.",
    },
    "🔄 Sync (V2)": {
        "tools": ["get_all_tasks", "full_sync"],
        "desc": "Full account sync — all projects, tasks, tags, folders in one call.",
    },
    "📦 Completed & Trash (V2)": {
        "tools": ["get_completed_tasks", "get_deleted_tasks"],
        "desc": "Access completed/abandoned tasks and trash.",
    },
    "📁 Folders (V2)": {
        "tools": ["list_project_folders", "manage_project_folders"],
        "desc": "Organize projects into folders/groups.",
    },
    "📊 Kanban Columns (V2)": {
        "tools": ["list_columns", "manage_columns"],
        "desc": "Manage kanban board columns within a project.",
    },
    "🏷️ Tags (V2)": {
        "tools": ["list_tags", "create_tag", "update_tag", "rename_tag", "merge_tags", "delete_tag"],
        "desc": "Full tag management: create, update, rename, merge, delete.",
    },
    "🔁 Habits (V2)": {
        "tools": ["list_habits", "list_habit_sections", "create_habit", "update_habit", "delete_habit", "habit_checkin", "get_habit_records"],
        "desc": "Habit tracking: create habits, check in, view streaks & records.",
    },
    "🍅 Focus / Pomodoro (V2)": {
        "tools": ["get_focus_stats"],
        "desc": "Focus session statistics: heatmap and per-tag distribution.",
    },
    "👤 User & Stats (V2)": {
        "tools": ["get_user_status", "get_productivity_stats"],
        "desc": "Account info, subscription status, productivity scores & streaks.",
    },
    "🛠️ Utilities": {
        "tools": ["ticktick_guide", "check_v2_availability", "build_recurrence_rule", "build_reminder"],
        "desc": "Helpers: tool catalog, V2 check, RRULE builder, reminder builder.",
    },
}

COMMON_WORKFLOWS = [
    {
        "name": "Create task with subtasks",
        "steps": [
            "1. create_task(title='Parent task', project_id='...')",
            "2. create_task(title='Subtask 1', project_id='...')",
            "3. set_subtask_parent(task_id=<subtask_id>, project_id='...', parent_id=<parent_id>)",
        ],
    },
    {
        "name": "Create recurring task with reminder",
        "steps": [
            "1. build_recurrence_rule(frequency='WEEKLY', by_day=['MO','WE','FR']) → get rrule",
            "2. create_task(title='...', recurrence=<rrule>, reminder_minutes=[30], due_date='...', time_zone='Europe/Paris')",
        ],
    },
    {
        "name": "Move tasks to a new project",
        "steps": [
            "1. create_project(name='New Project') → get project id",
            "2. move_tasks([{'taskId': '...', 'fromProjectId': '...', 'toProjectId': '<new_id>'}])",
        ],
    },
    {
        "name": "Organize with Eisenhower matrix",
        "steps": [
            "1. create_project(name='Eisenhower', view_mode='kanban')",
            "2. manage_columns(project_id='...', add=[{'name':'Urgent+Important'},{'name':'Important'},{'name':'Urgent'},{'name':'Neither'}])",
            "3. create_task(title='...', project_id='...', column_id='<column_id>', priority=5)",
        ],
    },
    {
        "name": "Track a measurable habit",
        "steps": [
            "1. create_habit(name='Drink water', habit_type='Real', goal=2.0, step=0.25, unit='L')",
            "2. habit_checkin(habit_id='...', checkin_stamp=20260306, value=0.5)",
            "3. get_habit_records(habit_ids=['...']) → view history",
        ],
    },
    {
        "name": "Full account overview",
        "steps": [
            "1. full_sync() → all projects, tasks, tags, folders in one call",
            "   OR list_projects() + get_all_tasks() for just projects & tasks",
        ],
    },
    {
        "name": "Add/update reminders on existing tasks (V1/V2 safe pattern)",
        "steps": [
            "1. get_task_detail(project_id='...', task_id='...') → inspect dueDate",
            "   ⚠️ V2-created tasks may show dueDate=null via V1 — read the raw value.",
            "2. update_task(task_id='...', project_id='...', due_date='<ISO8601>',",
            "               time_zone='Europe/Paris', reminder_minutes=[2880, 1440])",
            "   ← MUST pass due_date explicitly: V1 uses it as anchor to place reminders.",
            "   ← reminder_minutes=[2880] = J-2, [1440] = J-1, [0] = at due time.",
            "3. get_task_detail(...) → verify reminders field shows ['TRIGGER:-P2D', ...]",
            "   ⚠️ Do NOT use batch_update_tasks() for reminders — V2 batch cannot anchor",
            "     reminders when dueDate is null, and object format {trigger:} is silently rejected.",
        ],
    },
]

INTENT_GUIDE = {
    "know_what_to_do_today": {
        "description": "Get an actionable view of today's work, events, and carry-over.",
        "tools": ["tasks_of_today", "events_of_today", "overdue_tasks", "priority_dashboard"],
    },
    "plan_the_week": {
        "description": "Build a weekly planning view with timed events, due tasks, and overdue carry-over.",
        "tools": ["week_overview", "week_agenda", "upcoming_tasks", "save_query_preset", "run_query_preset"],
    },
    "find_a_note": {
        "description": "Search notes precisely with folder/project scoping and grep-like filters.",
        "tools": ["query_notes", "workspace_map", "query_projects", "query_folders", "save_query_preset"],
    },
    "find_tasks_precisely": {
        "description": "Filter tasks by project, tag, date range, regex, reminder state, recurrence, or hierarchy.",
        "tools": ["query_tasks", "query_agenda", "query_task_history", "list_query_presets", "run_query_preset"],
    },
    "reorganize_projects": {
        "description": "Inspect workspace structure, create/move projects safely, and verify folder placement.",
        "tools": ["workspace_map", "query_projects", "verified_create_project", "verified_assign_project_folder"],
    },
    "clean_up_tasks": {
        "description": "Surface stale, overdue, low-signal, or historical tasks before deciding what to archive or move.",
        "tools": ["stale_tasks", "overdue_tasks", "query_task_history", "priority_dashboard", "query_tasks"],
    },
    "perform_safe_structural_changes": {
        "description": "Use verified wrappers for known TickTick silent-failure zones such as subtasks, moves, and folder assignment.",
        "tools": [
            "create_subtask",
            "verified_set_subtask_parent",
            "verified_move_tasks",
            "verified_batch_move",
            "verified_assign_project_folder",
        ],
    },
}


def _err(e) -> dict:
    if isinstance(e, TickTickAPIError):
        return e.to_dict()
    return {"error": True, "message": str(e), "type": type(e).__name__}


def _task_dict(task) -> dict:
    d = task.model_dump(exclude_none=False)
    d["priority_label"] = task.priority_label()
    d["is_completed"] = task.is_completed()
    d["allDay"] = task.effective_all_day()
    progress = task.checklist_progress()
    if progress:
        d["checklist_progress"] = progress
    return d


def _model_list(items) -> list[dict]:
    return [i.model_dump(exclude_none=False) for i in (items or [])]


def _query_service() -> TickTickQueryService:
    return TickTickQueryService(client)


def _preset_store() -> QueryPresetStore:
    return QueryPresetStore(STATE_DIRECTORY)


def _normalize_str_list(value: StrListArg) -> Optional[list[str]]:
    """Normalize string-or-list inputs used by multi-value query filters."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _make_task_filter_spec(
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    tags: StrListArg = None,
    tag_mode: str = "any",
    text_query: Optional[str] = None,
    keyword_mode: str = "any",
    regex: Optional[str] = None,
    exclude_regex: Optional[str] = None,
    search_fields: StrListArg = None,
    due_from: Optional[str] = None,
    due_to: Optional[str] = None,
    start_from: Optional[str] = None,
    start_to: Optional[str] = None,
    modified_from: Optional[str] = None,
    modified_to: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    timed_only: bool = False,
    all_day: Optional[bool] = None,
    min_priority: Optional[int] = None,
    priorities: Optional[list[int]] = None,
    has_reminders: Optional[bool] = None,
    is_recurring: Optional[bool] = None,
    has_checklist: Optional[bool] = None,
    parent_only: bool = False,
    subtasks_only: bool = False,
    limit: int = 50,
    sort_by: str = "dueDate",
    descending: bool = False,
) -> TaskFilterSpec:
    return TaskFilterSpec(
        project_ids=_normalize_str_list(project_ids),
        project_names=_normalize_str_list(project_names),
        folder_ids=_normalize_str_list(folder_ids),
        folder_names=_normalize_str_list(folder_names),
        tags=_normalize_str_list(tags),
        tag_mode=tag_mode,
        text_query=text_query,
        keyword_mode=keyword_mode,
        regex=regex,
        exclude_regex=exclude_regex,
        search_fields=_normalize_str_list(search_fields),
        due_from=due_from,
        due_to=due_to,
        start_from=start_from,
        start_to=start_to,
        modified_from=modified_from,
        modified_to=modified_to,
        created_from=created_from,
        created_to=created_to,
        time_from=time_from,
        time_to=time_to,
        timed_only=timed_only,
        all_day=all_day,
        min_priority=min_priority,
        priorities=priorities,
        has_reminders=has_reminders,
        is_recurring=is_recurring,
        has_checklist=has_checklist,
        parent_only=parent_only,
        subtasks_only=subtasks_only,
        limit=limit,
        sort_by=sort_by,
        descending=descending,
    )


__all__ = [
    "mcp",
    "TOOL_CATALOG",
    "COMMON_WORKFLOWS",
    "INTENT_GUIDE",
    "_err",
    "_task_dict",
    "_model_list",
    "_query_service",
    "_preset_store",
    "_normalize_str_list",
    "StrListArg",
    "_make_task_filter_spec",
    "client",
    "TickTickAPIError",
    "Priority",
    "build_reminder_trigger",
    "build_rrule",
    "has_v2_auth",
    "ENV_SESSION_TOKEN",
    "SESSION_COOKIE_NAME",
]
