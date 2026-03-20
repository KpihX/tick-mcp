"""
Verified structural TickTick operations.

These wrappers execute a write operation and then re-read the affected entities
to prove the resulting structure matches the intention.
"""
from __future__ import annotations

from typing import Any, Optional

from .core import mcp, _err, _task_dict, client, TickTickAPIError


def _project_child_index(project_id: str) -> dict[str, list[str]]:
    data = client.get_project_data(project_id)
    return {
        task.id: (task.childIds or [])
        for task in data.tasks
        if task.id
    }


@mcp.tool()
def create_subtask(
    title: str,
    project_id: str,
    parent_id: str,
    content: Optional[str] = None,
    desc: Optional[str] = None,
    priority: Optional[int] = None,
    due_date: Optional[str] = None,
    start_date: Optional[str] = None,
    time_zone: Optional[str] = None,
    tags: Optional[list[str]] = None,
    checklist_items: Optional[list[str]] = None,
    all_day: Optional[bool] = None,
    kind: Optional[str] = None,
    reminder_minutes: Optional[list[int]] = None,
    recurrence: Optional[str] = None,
    column_id: Optional[str] = None,
) -> dict:
    """
    Create a child task and verify the parent-child relationship afterwards.

    [Category: Verified Actions]  [Auth: V1 + V2]
    [Related: create_task, set_subtask_parent, verified_set_subtask_parent]
    """
    from ..server import create_task, set_subtask_parent

    try:
        created = create_task(
            title=title,
            project_id=project_id,
            content=content,
            desc=desc,
            priority=priority,
            due_date=due_date,
            start_date=start_date,
            time_zone=time_zone,
            tags=tags,
            checklist_items=checklist_items,
            all_day=all_day,
            kind=kind,
            reminder_minutes=reminder_minutes,
            recurrence=recurrence,
            column_id=column_id,
        )
        if created.get("error"):
            return created

        task_id = created["id"]
        linked = set_subtask_parent(task_id=task_id, project_id=project_id, parent_id=parent_id)
        if linked.get("error"):
            return linked

        child = client.get_task(project_id, task_id)
        child_index = _project_child_index(project_id)
        parent_child_ids = child_index.get(parent_id, [])
        verified = child.parentId == parent_id and task_id in parent_child_ids
        result = {
            "verified": verified,
            "created": _task_dict(child),
            "verification": {
                "child_parent_id": child.parentId,
                "expected_parent_id": parent_id,
                "parent_child_ids": parent_child_ids,
            },
        }
        if not verified:
            result["error"] = True
            result["message"] = "Subtask relationship did not verify after creation."
        return result
    except TickTickAPIError as e:
        return _err(e)


@mcp.tool()
def verified_create_project(
    name: str,
    color: Optional[str] = None,
    kind: str = "TASK",
    view_mode: Optional[str] = None,
    group_id: Optional[str] = None,
) -> dict:
    """
    Create a project, then verify that it exists and that folder assignment persisted if requested.

    [Category: Verified Actions]  [Auth: V1 + V2 when group_id is provided]
    [Related: create_project, verified_assign_project_folder]
    """
    from ..server import create_project

    try:
        result = create_project(
            name=name,
            color=color,
            kind=kind,
            view_mode=view_mode,
            group_id=group_id,
        )
        if result.get("error"):
            return result

        project_id = result["id"]
        project = client.get_project(project_id).model_dump(exclude_none=False)
        verification = {
            "exists_in_v1": bool(project),
            "requested_group_id": group_id,
        }
        verified = bool(project)
        sync_project = None
        if group_id is not None:
            sync_state = client.sync_all()
            sync_project = next(
                (item.model_dump(exclude_none=False) for item in sync_state.projectProfiles if item.id == project_id),
                None,
            )
            verification["group_id_persisted_v2"] = bool(sync_project) and sync_project.get("groupId") == group_id
            verified = verified and bool(verification["group_id_persisted_v2"])

        output = {
            "verified": verified,
            "project": project,
            "sync_project": sync_project,
            "verification": verification,
        }
        if not verified:
            output["error"] = True
            output["message"] = "Project creation did not fully verify."
        return output
    except TickTickAPIError as e:
        return _err(e)


@mcp.tool()
def verified_set_subtask_parent(
    task_id: str,
    project_id: str,
    parent_id: Optional[str] = None,
    old_parent_id: Optional[str] = None,
) -> dict:
    """
    Set or unset a parent relationship, then verify the resulting structure.

    [Category: Verified Actions]  [Auth: V2]
    [Related: set_subtask_parent, create_subtask]
    """
    from ..server import set_subtask_parent

    try:
        result = set_subtask_parent(
            task_id=task_id,
            project_id=project_id,
            parent_id=parent_id,
            old_parent_id=old_parent_id,
        )
        if result.get("error"):
            return result

        child = client.get_task(project_id, task_id)
        child_index = _project_child_index(project_id)

        if parent_id:
            verified = child.parentId == parent_id and task_id in child_index.get(parent_id, [])
        else:
            verified = child.parentId in (None, "") and task_id not in child_index.get(old_parent_id or "", [])

        response = {
            "verified": verified,
            "child": _task_dict(child),
            "parent_id": parent_id,
            "old_parent_id": old_parent_id,
        }
        if not verified:
            response["error"] = True
            response["message"] = "Parent relationship did not verify after update."
        return response
    except TickTickAPIError as e:
        return _err(e)


@mcp.tool()
def verified_move_tasks(moves: list[dict]) -> dict:
    """
    Move tasks, then verify that each moved task is present in the destination project.

    [Category: Verified Actions]  [Auth: V2]
    [Related: move_tasks, set_subtask_parent]
    """
    from ..server import move_tasks

    try:
        result = move_tasks(moves)
        if result.get("error"):
            return result

        augmented_moves = list(moves)
        if "cascaded_children" in result:
            augmented_moves.extend(result["cascaded_children"])

        destination_map: dict[str, set[str]] = {}
        for move in augmented_moves:
            destination_map.setdefault(move["toProjectId"], set()).add(move["taskId"])

        verification: list[dict[str, Any]] = []
        verified = True
        for project_id, task_ids in destination_map.items():
            destination_tasks = {task.id for task in client.get_project_data(project_id).tasks if task.id}
            missing = sorted(task_id for task_id in task_ids if task_id not in destination_tasks)
            verification.append(
                {
                    "project_id": project_id,
                    "expected_task_ids": sorted(task_ids),
                    "missing_task_ids": missing,
                }
            )
            if missing:
                verified = False

        output = {
            "verified": verified,
            "result": result,
            "verification": verification,
        }
        if not verified:
            output["error"] = True
            output["message"] = "One or more moved tasks were not found in the destination projects."
        return output
    except TickTickAPIError as e:
        return _err(e)


@mcp.tool()
def verified_batch_move(moves: list[dict]) -> dict:
    """
    Verified batch move wrapper with rollback hints if verification fails.

    [Category: Verified Actions]  [Auth: V2]
    [Related: verified_move_tasks, move_tasks]
    """
    result = verified_move_tasks(moves)
    if result.get("error"):
        rollback_moves = [
            {
                "taskId": move["taskId"],
                "fromProjectId": move["toProjectId"],
                "toProjectId": move["fromProjectId"],
            }
            for move in moves
        ]
        result["rollback_hint"] = {
            "tool": "move_tasks",
            "moves": rollback_moves,
            "note": "Run the rollback moves only after checking which tasks were actually moved.",
        }
    return result


@mcp.tool()
def verified_assign_project_folder(project_id: str, group_id: str) -> dict:
    """
    Assign a project to a folder and verify the persisted groupId through V2 sync.

    [Category: Verified Actions]  [Auth: V1 + V2]
    [Related: update_project, list_project_folders, full_sync]
    """
    from ..server import update_project

    try:
        before_sync = client.sync_all()
        before = next(
            (project.model_dump(exclude_none=False) for project in before_sync.projectProfiles if project.id == project_id),
            None,
        )
        result = update_project(project_id=project_id, group_id=group_id)
        if result.get("error"):
            return result

        after_sync = client.sync_all()
        after = next(
            (project.model_dump(exclude_none=False) for project in after_sync.projectProfiles if project.id == project_id),
            None,
        )
        verified = bool(after) and after.get("groupId") == group_id
        output = {
            "verified": verified,
            "before": before,
            "after": after,
            "requested_group_id": group_id,
        }
        if not verified:
            output["error"] = True
            output["message"] = "Project folder assignment did not verify through V2 sync."
        return output
    except TickTickAPIError as e:
        return _err(e)
