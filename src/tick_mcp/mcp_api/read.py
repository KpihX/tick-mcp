"""
High-level read/query MCP tools for TickTick.

This module is imported by `server.py` after the shared helpers are defined.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any, Optional

from .core import (
    mcp,
    _err,
    _query_service,
    _preset_store,
    _make_task_filter_spec,
    _normalize_str_list,
    StrListArg,
    TickTickAPIError,
)


def _local_day_bounds(raw_date: Optional[str]) -> tuple[str, str]:
    if raw_date:
        day = datetime.fromisoformat(raw_date).date()
    else:
        day = datetime.now().astimezone().date()
    start = datetime.combine(day, datetime.min.time())
    end = datetime.combine(day, datetime.max.time()).replace(microsecond=0)
    return start.isoformat(), end.isoformat()


def _local_range_bounds(raw_date: Optional[str], days: int) -> tuple[str, str]:
    if days < 1:
        raise ValueError("days must be >= 1.")
    if raw_date:
        start_day = datetime.fromisoformat(raw_date).date()
    else:
        start_day = datetime.now().astimezone().date()
    end_day = start_day + timedelta(days=days - 1)
    start = datetime.combine(start_day, datetime.min.time())
    end = datetime.combine(end_day, datetime.max.time()).replace(microsecond=0)
    return start.isoformat(), end.isoformat()


@mcp.tool()
def workspace_map(
    include_closed: bool = False,
    include_counts: bool = False,
    project_name_query: Optional[str] = None,
    project_regex: Optional[str] = None,
    folder_name_query: Optional[str] = None,
    folder_regex: Optional[str] = None,
) -> dict:
    """
    Return a navigable map of folders and projects, optionally with active task counts.

    [Category: Query & Search]  [Auth: V1 + V2 when include_counts=True]
    [Related: list_projects, list_project_folders, full_sync, query_projects]
    """
    try:
        return _query_service().workspace_map(
            include_closed=include_closed,
            include_counts=include_counts,
            project_name_query=project_name_query,
            project_regex=project_regex,
            folder_name_query=folder_name_query,
            folder_regex=folder_regex,
        )
    except (TickTickAPIError, ValueError) as e:
        return _err(e)


@mcp.tool()
def query_projects(
    name_query: Optional[str] = None,
    regex: Optional[str] = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    kinds: StrListArg = None,
    include_closed: bool = False,
    limit: int = 50,
    sort_by: str = "name",
    descending: bool = False,
) -> dict:
    """
    Search/filter projects with folder-aware metadata.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: workspace_map, list_projects, list_project_folders, query_folders]
    Multi-value filters accept either a list or a single string.
    """
    try:
        return _query_service().query_projects(
            name_query=name_query,
            regex=regex,
            folder_ids=_normalize_str_list(folder_ids),
            folder_names=_normalize_str_list(folder_names),
            kinds=_normalize_str_list(kinds),
            include_closed=include_closed,
            limit=limit,
            sort_by=sort_by,
            descending=descending,
        )
    except (TickTickAPIError, ValueError, re.error) as e:
        return _err(e)


@mcp.tool()
def query_folders(
    name_query: Optional[str] = None,
    regex: Optional[str] = None,
    include_project_counts: bool = True,
    limit: int = 50,
) -> dict:
    """
    Search/filter project folders with optional project counts.

    [Category: Query & Search]  [Auth: V1 + V2 when include_project_counts=True]
    [Related: workspace_map, list_project_folders, query_projects]
    """
    try:
        return _query_service().query_folders(
            name_query=name_query,
            regex=regex,
            include_project_counts=include_project_counts,
            limit=limit,
        )
    except (TickTickAPIError, ValueError, re.error) as e:
        return _err(e)


@mcp.tool()
def query_tasks(
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
) -> dict:
    """
    Query active tasks with fine-grained filters, date/hour ranges, and grep-like matching.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: query_notes, query_agenda, get_all_tasks, get_project_tasks]
    Multi-value filters accept either a list or a single string.
    """
    try:
        spec = _make_task_filter_spec(
            project_ids=project_ids,
            project_names=project_names,
            folder_ids=folder_ids,
            folder_names=folder_names,
            tags=tags,
            tag_mode=tag_mode,
            text_query=text_query,
            keyword_mode=keyword_mode,
            regex=regex,
            exclude_regex=exclude_regex,
            search_fields=search_fields,
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
        return _query_service().query_tasks(spec)
    except (TickTickAPIError, ValueError, re.error) as e:
        return _err(e)


@mcp.tool()
def query_notes(
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    text_query: Optional[str] = None,
    keyword_mode: str = "any",
    regex: Optional[str] = None,
    exclude_regex: Optional[str] = None,
    search_fields: StrListArg = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    modified_from: Optional[str] = None,
    modified_to: Optional[str] = None,
    limit: int = 50,
    sort_by: str = "modifiedTime",
    descending: bool = True,
) -> dict:
    """
    Query notes with folder/project scope and grep-like content search.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: query_tasks, workspace_map, get_project_tasks]
    Multi-value filters accept either a list or a single string.
    """
    try:
        spec = _make_task_filter_spec(
            project_ids=project_ids,
            project_names=project_names,
            folder_ids=folder_ids,
            folder_names=folder_names,
            text_query=text_query,
            keyword_mode=keyword_mode,
            regex=regex,
            exclude_regex=exclude_regex,
            search_fields=search_fields,
            created_from=created_from,
            created_to=created_to,
            modified_from=modified_from,
            modified_to=modified_to,
            limit=limit,
            sort_by=sort_by,
            descending=descending,
        )
        return _query_service().query_notes(spec)
    except (TickTickAPIError, ValueError, re.error) as e:
        return _err(e)


@mcp.tool()
def query_agenda(
    from_dt: str,
    to_dt: str,
    date_field: str = "scheduled",
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
) -> dict:
    """
    Query scheduled items inside a date/time window.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: query_tasks, get_all_tasks, get_project_tasks]
    Multi-value filters accept either a list or a single string.
    """
    try:
        spec = _make_task_filter_spec(
            project_ids=project_ids,
            project_names=project_names,
            folder_ids=folder_ids,
            folder_names=folder_names,
            tags=tags,
            tag_mode=tag_mode,
            text_query=text_query,
            keyword_mode=keyword_mode,
            regex=regex,
            exclude_regex=exclude_regex,
            search_fields=search_fields,
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
        return _query_service().query_agenda(from_dt=from_dt, to_dt=to_dt, spec=spec, date_field=date_field)
    except (TickTickAPIError, ValueError, re.error) as e:
        return _err(e)


@mcp.tool()
def tasks_of_today(
    local_date: Optional[str] = None,
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    tags: StrListArg = None,
    text_query: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """
    Return active tasks scheduled for a given local day.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: query_agenda, events_of_today, overdue_tasks]
    Multi-value filters accept either a list or a single string.
    """
    start, end = _local_day_bounds(local_date)
    return query_agenda(
        from_dt=start,
        to_dt=end,
        date_field="scheduled",
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        limit=limit,
        sort_by="dueDate",
        descending=False,
    )


@mcp.tool()
def events_of_today(
    local_date: Optional[str] = None,
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    tags: StrListArg = None,
    text_query: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """
    Return timed scheduled items for a given local day.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: tasks_of_today, query_agenda]
    Multi-value filters accept either a list or a single string.
    """
    start, end = _local_day_bounds(local_date)
    return query_agenda(
        from_dt=start,
        to_dt=end,
        date_field="scheduled",
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        time_from=time_from,
        time_to=time_to,
        timed_only=True,
        limit=limit,
        sort_by="dueDate",
        descending=False,
    )


@mcp.tool()
def week_overview(
    local_date: Optional[str] = None,
    days: int = 7,
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    tags: StrListArg = None,
    text_query: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    limit_per_section: int = 50,
) -> dict:
    """
    Return a planning-oriented overview split into events, due tasks, and overdue tasks.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: week_agenda, upcoming_tasks, overdue_tasks]
    Multi-value filters accept either a list or a single string.
    """
    events = week_agenda(
        local_date=local_date,
        days=days,
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        timed_only=True,
        time_from=time_from,
        time_to=time_to,
        limit=limit_per_section,
    )
    due_tasks = upcoming_tasks(
        local_date=local_date,
        days=days,
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        limit=limit_per_section,
    )
    overdue = overdue_tasks(
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        limit=limit_per_section,
    )
    return {
        "window": {"local_date": local_date, "days": days},
        "scope": {
            "project_ids": project_ids,
            "project_names": project_names,
            "folder_ids": folder_ids,
            "folder_names": folder_names,
            "tags": tags,
            "text_query": text_query,
        },
        "events": events,
        "due_tasks": due_tasks,
        "overdue": overdue,
    }


@mcp.tool()
def week_agenda(
    local_date: Optional[str] = None,
    days: int = 7,
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    tags: StrListArg = None,
    text_query: Optional[str] = None,
    timed_only: bool = False,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """
    Return scheduled items for a local multi-day window (default: 7 days).

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: query_agenda, tasks_of_today, events_of_today]
    Multi-value filters accept either a list or a single string.
    """
    start, end = _local_range_bounds(local_date, days)
    return query_agenda(
        from_dt=start,
        to_dt=end,
        date_field="scheduled",
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        timed_only=timed_only,
        time_from=time_from,
        time_to=time_to,
        limit=limit,
        sort_by="dueDate",
        descending=False,
    )


@mcp.tool()
def upcoming_tasks(
    local_date: Optional[str] = None,
    days: int = 7,
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    tags: StrListArg = None,
    text_query: Optional[str] = None,
    min_priority: Optional[int] = None,
    priorities: Optional[list[int]] = None,
    limit: int = 100,
) -> dict:
    """
    Return active tasks due within a local upcoming window.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: query_tasks, week_agenda, overdue_tasks]
    Multi-value filters accept either a list or a single string.
    """
    due_from, due_to = _local_range_bounds(local_date, days)
    return query_tasks(
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        due_from=due_from,
        due_to=due_to,
        min_priority=min_priority,
        priorities=priorities,
        limit=limit,
        sort_by="dueDate",
        descending=False,
    )


@mcp.tool()
def overdue_tasks(
    before_dt: Optional[str] = None,
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    tags: StrListArg = None,
    text_query: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """
    Return active tasks whose due date is already in the past.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: tasks_of_today, query_tasks, stale_tasks]
    Multi-value filters accept either a list or a single string.
    """
    now = before_dt or datetime.now().astimezone().replace(microsecond=0).isoformat()
    return query_tasks(
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        due_to=now,
        limit=limit,
        sort_by="dueDate",
        descending=False,
    )


@mcp.tool()
def stale_tasks(
    older_than_days: int = 30,
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    tags: StrListArg = None,
    text_query: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """
    Return active tasks that have not been modified recently.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: query_tasks, overdue_tasks]
    Multi-value filters accept either a list or a single string.
    """
    threshold = datetime.now().astimezone().replace(microsecond=0) - timedelta(days=older_than_days)
    return query_tasks(
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        modified_to=threshold.isoformat(),
        limit=limit,
        sort_by="modifiedTime",
        descending=False,
    )


@mcp.tool()
def priority_dashboard(
    project_ids: StrListArg = None,
    project_names: StrListArg = None,
    folder_ids: StrListArg = None,
    folder_names: StrListArg = None,
    tags: StrListArg = None,
    text_query: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """
    Summarize active tasks by priority with top items per bucket.

    [Category: Query & Search]  [Auth: V1 + V2]
    [Related: query_tasks, tasks_of_today, overdue_tasks]
    Multi-value filters accept either a list or a single string.
    """
    result = query_tasks(
        project_ids=project_ids,
        project_names=project_names,
        folder_ids=folder_ids,
        folder_names=folder_names,
        tags=tags,
        text_query=text_query,
        limit=limit,
        sort_by="priority",
        descending=True,
    )
    if result.get("error"):
        return result

    buckets: dict[str, dict[str, object]] = {
        "high": {"count": 0, "items": []},
        "medium": {"count": 0, "items": []},
        "low": {"count": 0, "items": []},
        "none": {"count": 0, "items": []},
    }
    for item in result["items"]:
        label = str(item.get("priority_label", "none"))
        bucket = buckets.setdefault(label, {"count": 0, "items": []})
        bucket["count"] = int(bucket["count"]) + 1
        items = bucket["items"]
        if isinstance(items, list) and len(items) < 5:
            items.append(item)

    return {
        "scope": {
            "project_ids": project_ids,
            "project_names": project_names,
            "folder_ids": folder_ids,
            "folder_names": folder_names,
            "tags": tags,
            "text_query": text_query,
        },
        "count": result["count"],
        "plan": result.get("plan"),
        "buckets": buckets,
    }


@mcp.tool()
def list_query_presets() -> dict:
    """
    List saved reusable query presets.

    [Category: Query & Search]  [Auth: none]
    [Related: save_query_preset, run_query_preset, delete_query_preset]
    """
    try:
        return _preset_store().list_presets()
    except ValueError as e:
        return _err(e)


@mcp.tool()
def save_query_preset(
    name: str,
    query_type: str,
    filters: dict[str, Any],
    description: Optional[str] = None,
) -> dict:
    """
    Save a reusable query preset.

    [Category: Query & Search]  [Auth: none]
    [Related: list_query_presets, run_query_preset, delete_query_preset]
    """
    try:
        return _preset_store().save_preset(
            name=name,
            query_type=query_type,
            filters=filters,
            description=description,
        )
    except ValueError as e:
        return _err(e)


@mcp.tool()
def run_query_preset(name: str, limit_override: Optional[int] = None) -> dict:
    """
    Execute a saved query preset.

    [Category: Query & Search]  [Auth: depends on preset query type]
    [Related: list_query_presets, save_query_preset, delete_query_preset]
    """
    try:
        preset = _preset_store().get_preset(name)
        query_type = preset["query_type"]
        filters = dict(preset.get("filters") or {})
        if limit_override is not None:
            filters["limit"] = limit_override

        if query_type == "tasks":
            result = query_tasks(**filters)
        elif query_type == "notes":
            result = query_notes(**filters)
        elif query_type == "agenda":
            result = query_agenda(**filters)
        elif query_type == "history":
            result = query_task_history(**filters)
        elif query_type == "week_overview":
            result = week_overview(**filters)
        elif query_type == "priority_dashboard":
            result = priority_dashboard(**filters)
        else:
            return _err(ValueError(f"Unsupported preset query_type '{query_type}'"))

        return {
            "preset": preset,
            "result": result,
        }
    except ValueError as e:
        return _err(e)


@mcp.tool()
def delete_query_preset(name: str) -> dict:
    """
    Delete a saved query preset.

    [Category: Query & Search]  [Auth: none]
    [Related: list_query_presets, save_query_preset, run_query_preset]
    """
    try:
        return _preset_store().delete_preset(name)
    except ValueError as e:
        return _err(e)


@mcp.tool()
def query_task_history(
    history_source: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
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
    sort_by: str = "completedTime",
    descending: bool = True,
) -> dict:
    """
    Query completed, abandoned, or deleted task history with the same fine filters.

    [Category: Query & Search]  [Auth: V2]
    [Related: get_completed_tasks, get_deleted_tasks, query_tasks]
    Multi-value filters accept either a list or a single string.
    """
    try:
        spec = _make_task_filter_spec(
            project_ids=project_ids,
            project_names=project_names,
            folder_ids=folder_ids,
            folder_names=folder_names,
            tags=tags,
            tag_mode=tag_mode,
            text_query=text_query,
            keyword_mode=keyword_mode,
            regex=regex,
            exclude_regex=exclude_regex,
            search_fields=search_fields,
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
        return _query_service().query_task_history(
            history_source=history_source,
            from_date=from_date,
            to_date=to_date,
            spec=spec,
        )
    except (TickTickAPIError, ValueError, re.error) as e:
        return _err(e)
