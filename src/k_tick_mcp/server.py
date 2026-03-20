"""
TickTick MCP public server surface.

This module keeps the stable import location used by the CLI entrypoint and by
existing tests, while the actual tool groups live in dedicated modules under
`k_tick_mcp.mcp_api`.
"""
from __future__ import annotations

from .mcp_api.core import (
    mcp,
    TOOL_CATALOG,
    COMMON_WORKFLOWS,
    _err,
    _task_dict,
)
from .mcp_api.utilities import ticktick_guide, check_v2_availability, build_recurrence_rule, build_reminder
from .mcp_api.projects import list_projects, get_project_detail, create_project, update_project, delete_project
from .mcp_api.tasks_read import get_inbox, get_project_tasks, get_task_detail
from .mcp_api.tasks_write import create_task, update_task, complete_task, reopen_task, delete_task
from .mcp_api.sync_api import get_all_tasks, full_sync
from .mcp_api.tasks_batch import batch_create_tasks, batch_update_tasks, batch_delete_tasks, move_tasks, set_subtask_parent
from .mcp_api.history import get_completed_tasks, get_deleted_tasks
from .mcp_api.folders import list_project_folders, manage_project_folders, list_columns, manage_columns
from .mcp_api.tags import list_tags, create_tag, update_tag, rename_tag, merge_tags, delete_tag
from .mcp_api.habits import list_habits, list_habit_sections, create_habit, update_habit, delete_habit, habit_checkin, get_habit_records
from .mcp_api.stats import get_focus_stats, get_user_status, get_productivity_stats
from .mcp_api.read import (
    workspace_map,
    query_projects,
    query_folders,
    query_tasks,
    query_notes,
    query_agenda,
    tasks_of_today,
    events_of_today,
    week_agenda,
    week_overview,
    upcoming_tasks,
    overdue_tasks,
    stale_tasks,
    priority_dashboard,
    list_query_presets,
    save_query_preset,
    run_query_preset,
    delete_query_preset,
    query_task_history,
)
from .mcp_api.verified import (
    create_subtask,
    verified_create_project,
    verified_set_subtask_parent,
    verified_move_tasks,
    verified_batch_move,
    verified_assign_project_folder,
)

__all__ = [
    'mcp',
    'TOOL_CATALOG',
    'COMMON_WORKFLOWS',
    '_err',
    '_task_dict',
    'ticktick_guide',
    'check_v2_availability',
    'build_recurrence_rule',
    'build_reminder',
    'list_projects',
    'get_project_detail',
    'create_project',
    'update_project',
    'delete_project',
    'get_inbox',
    'get_project_tasks',
    'get_task_detail',
    'create_task',
    'update_task',
    'complete_task',
    'reopen_task',
    'delete_task',
    'get_all_tasks',
    'full_sync',
    'batch_create_tasks',
    'batch_update_tasks',
    'batch_delete_tasks',
    'move_tasks',
    'set_subtask_parent',
    'get_completed_tasks',
    'get_deleted_tasks',
    'list_project_folders',
    'manage_project_folders',
    'list_columns',
    'manage_columns',
    'list_tags',
    'create_tag',
    'update_tag',
    'rename_tag',
    'merge_tags',
    'delete_tag',
    'list_habits',
    'list_habit_sections',
    'create_habit',
    'update_habit',
    'delete_habit',
    'habit_checkin',
    'get_habit_records',
    'get_focus_stats',
    'get_user_status',
    'get_productivity_stats',
    'workspace_map',
    'query_projects',
    'query_folders',
    'query_tasks',
    'query_notes',
    'query_agenda',
    'tasks_of_today',
    'events_of_today',
    'week_agenda',
    'week_overview',
    'upcoming_tasks',
    'overdue_tasks',
    'stale_tasks',
    'priority_dashboard',
    'list_query_presets',
    'save_query_preset',
    'run_query_preset',
    'delete_query_preset',
    'query_task_history',
    'create_subtask',
    'verified_create_project',
    'verified_set_subtask_parent',
    'verified_move_tasks',
    'verified_batch_move',
    'verified_assign_project_folder',
]
