"""Utility and discovery MCP tools."""
from __future__ import annotations

from typing import Any, Optional

from .core import (
    mcp,
    TOOL_CATALOG,
    COMMON_WORKFLOWS,
    INTENT_GUIDE,
    _err,
    _task_dict,
    _model_list,
    client,
    TickTickAPIError,
    Priority,
    has_v2_auth,
    ENV_SESSION_TOKEN,
    SESSION_COOKIE_NAME,
    build_reminder_trigger,
    build_rrule,
)

@mcp.tool()
def ticktick_guide(
    category: Optional[str] = None,
    intent: Optional[str] = None,
    show_workflows: bool = False,
) -> dict:
    """
    Interactive guide to all TickTick MCP tools — START HERE.

    [Category: Utilities]  [Auth: none]
    [Related: check_v2_availability]

    Call with no args to see all categories and tool names.
    Call with a category name to see tools in that category.
    Call with an intent name to see the recommended tool path for a real user goal.
    Call with show_workflows=True to see common multi-step patterns.

    Args:
        category: Filter by category name (partial match, case-insensitive).
            Examples: "task", "tag", "habit", "project", "sync", "focus".
        intent: Filter by user intent, e.g. "know_what_to_do_today", "find_a_note",
            "reorganize_projects", or "clean_up_tasks".
        show_workflows: If True, return common multi-step workflow recipes.

      Tip: Call check_v2_availability() to see which features need a session token.
      Query filter ergonomics: for multi-value string filters (project/folder IDs or
      names, tags, search_fields, kinds), tools accept either a single string or a list.

    ── AGENT OPERATING CONTRACT ─────────────────────────────────────────────────
    The TickTick API is dual-layer (V1 official + V2 unofficial) with silent failure
    modes. Agents MUST apply the following discipline on every interaction:

    1. VERIFY AFTER EVERY WRITE: After create/update/delete operations, always call
       get_task_detail() (or equivalent read tool) to confirm the server state
       matches the intent. Do not trust API response codes alone — silent partial
       failures are common (reminders, parentId, groupId).

    2. RETRY UNTIL CONFIRMED: If verification reveals a mismatch, diagnose the root
       cause (V1/V2 API duality, missing anchor field, wrong format), adjust the
       call strategy, and retry. Repeat verify → fix → retry until state is correct.

    3. PROACTIVE USER FEEDBACK: After completing a multi-step task or recovering
       from a silent failure, report to the user:
         - What was attempted and what the API actually accepted.
         - Any workaround applied (e.g., switched from V2 batch to V1 update_task).
         - Recommendations for future similar operations.

    4. KNOWN SILENT FAILURE PATTERNS (see individual tool docs for details):
         - reminder_minutes on V2-created tasks → requires explicit due_date anchor
           in update_task() V1; batch_update_tasks() V2 cannot anchor reminders.
         - parentId at task creation → always silently ignored; use set_subtask_parent.
         - groupId at project creation → use V2 batch/project to set folder after.
         - reminder object format {trigger:} → silently rejected; use update_task V1.
    ─────────────────────────────────────────────────────────────────────────────
    """
    if show_workflows:
        return {"workflows": COMMON_WORKFLOWS}

    if intent:
        intent_key = intent.strip().lower()
        if intent_key in INTENT_GUIDE:
            payload = INTENT_GUIDE[intent_key]
            return {"intent": intent_key, **payload}
        return {
            "error": False,
            "message": (
                f"No intent matching '{intent}'. Available: {sorted(INTENT_GUIDE.keys())}"
            ),
        }

    if category:
        cat_lower = category.lower()
        filtered = {
            k: v for k, v in TOOL_CATALOG.items()
            if cat_lower in k.lower() or cat_lower in v["desc"].lower()
        }
        if not filtered:
            return {
                "error": False,
                "message": f"No category matching '{category}'. Available: {list(TOOL_CATALOG.keys())}",
            }
        return {"categories": filtered}

    # Full catalog — summary view
    summary = {}
    total = 0
    for cat, info in TOOL_CATALOG.items():
        summary[cat] = {"description": info["desc"], "tools": info["tools"], "count": len(info["tools"])}
        total += len(info["tools"])
    return {
        "total_tools": total,
        "categories": summary,
        "intents": INTENT_GUIDE,
        "query_filter_ergonomics": (
            "Multi-value string filters accept either a single string or a list. "
            "Example: folder_names='🎓 X' or folder_names=['🎓 X']."
        ),
        "tip": (
            "Call ticktick_guide(category='tasks') to drill into a category, "
            "ticktick_guide(intent='know_what_to_do_today') for a goal-oriented path, "
            "or ticktick_guide(show_workflows=True) for step-by-step recipes."
        ),
    }


@mcp.tool()
def check_v2_availability() -> dict:
    """
    Check whether V2 API features are available (session token configured).

    [Category: Utilities]  [Auth: none]
    [Related: ticktick_guide]

    Returns availability status and lists all V2-only feature categories.
    """
    available = has_v2_auth()
    v2_categories = [k for k in TOOL_CATALOG if "(V2)" in k]
    return {
        "v2_available": available,
        "message": "V2 features are enabled." if available else
                   f"V2 features unavailable. Set {ENV_SESSION_TOKEN} env var (extract '{SESSION_COOKIE_NAME}' cookie from TickTick web session).",
        "v2_categories": v2_categories,
    }


@mcp.tool()
def build_recurrence_rule(
    frequency: str,
    interval: int = 1,
    by_day: Optional[list[str]] = None,
    by_month_day: Optional[int] = None,
    by_month: Optional[int] = None,
    count: Optional[int] = None,
    until: Optional[str] = None,
) -> dict:
    """
    Build an iCalendar RRULE string for recurring tasks or habits.

    [Category: Utilities]  [Auth: none]
    [Related: create_task, update_task, create_habit]

    Args:
        frequency: "DAILY", "WEEKLY", "MONTHLY", or "YEARLY".
        interval: Repeat every N units (default 1).
        by_day: Weekday codes for WEEKLY, e.g. ["MO","WE","FR"].
        by_month_day: Day of month (1-31) for MONTHLY.
        by_month: Month number (1-12) for YEARLY.
        count: End after N occurrences.
        until: End date UTC: "20261231T000000Z".

    Examples:
        Every day          → frequency="DAILY"
        Mon/Wed/Fri        → frequency="WEEKLY", by_day=["MO","WE","FR"]
        15th of each month → frequency="MONTHLY", by_month_day=15
        Every 2 weeks      → frequency="WEEKLY", interval=2
        3 times then stop  → frequency="DAILY", count=3

    Returns {"rrule": "RRULE:FREQ=..."} — pass the rrule value as the
    'recurrence' parameter in create_task/update_task.
    """
    rule = build_rrule(
        frequency=frequency, interval=interval, by_day=by_day,
        by_month_day=by_month_day, by_month=by_month,
        count=count, until=until,
    )
    return {"rrule": rule}


@mcp.tool()
def build_reminder(minutes_before: int) -> dict:
    """
    Convert minutes into an iCalendar TRIGGER string for reminders.

    [Category: Utilities]  [Auth: none]
    [Related: create_task, update_task]

    Args:
        minutes_before: 0=at due time, 30=30min before, 60=1hr, 1440=1day, 2880=2days.

    Usually you don't need this — use the reminder_minutes parameter in create_task
    / update_task directly. This tool is for inspection or manual trigger building.
    """
    trigger = build_reminder_trigger(minutes_before)
    return {"trigger": trigger, "minutes_before": minutes_before}


# ═══════════════════════════════════════════════════════════════════════════════
#  📋 PROJECTS — V1
# ═══════════════════════════════════════════════════════════════════════════════
