"""
Unit tests for high-level views, presets, and verified structural wrappers.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tick_mcp.mcp_api import read, verified
from tick_mcp import server as server_mod
from tick_mcp.models import Project, ProjectData, Task


@pytest.mark.unit
class TestReadViews:
    def test_query_projects_accepts_single_string_filters(self, monkeypatch):
        captured = {}

        class FakeService:
            def query_projects(self, **kwargs):
                captured.update(kwargs)
                return {"count": 0, "items": []}

        monkeypatch.setattr(read, "_query_service", lambda: FakeService())
        read.query_projects(folder_names="🎓 X", folder_ids="folder-1", kinds="TASK")

        assert captured["folder_names"] == ["🎓 X"]
        assert captured["folder_ids"] == ["folder-1"]
        assert captured["kinds"] == ["TASK"]

    def test_query_tasks_accepts_single_string_filters(self, monkeypatch):
        captured = {}

        class FakeService:
            def query_tasks(self, spec):
                captured["spec"] = spec
                return {"count": 0, "items": []}

        monkeypatch.setattr(read, "_query_service", lambda: FakeService())
        read.query_tasks(
            project_names="Agenda",
            folder_names="🎓 X",
            tags="exam",
            search_fields="title",
        )

        spec = captured["spec"]
        assert spec.project_names == ["Agenda"]
        assert spec.folder_names == ["🎓 X"]
        assert spec.tags == ["exam"]
        assert spec.search_fields == ["title"]

    def test_query_agenda_accepts_single_string_filters(self, monkeypatch):
        captured = {}

        class FakeService:
            def query_agenda(self, **kwargs):
                captured.update(kwargs)
                return {"count": 0, "items": []}

        monkeypatch.setattr(read, "_query_service", lambda: FakeService())
        read.query_agenda(
            from_dt="2026-03-01T00:00:00",
            to_dt="2026-03-31T23:59:59",
            folder_names="🎓 X",
            project_names="📅 Agenda",
            tags="exam",
            search_fields="title",
        )

        spec = captured["spec"]
        assert spec.folder_names == ["🎓 X"]
        assert spec.project_names == ["📅 Agenda"]
        assert spec.tags == ["exam"]
        assert spec.search_fields == ["title"]

    def test_tasks_of_today_delegates_to_query_agenda(self, monkeypatch):
        captured = {}

        def fake_query_agenda(**kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

        monkeypatch.setattr(read, "query_agenda", fake_query_agenda)
        read.tasks_of_today(local_date="2026-03-20", project_names=["Agenda"])

        assert captured["date_field"] == "scheduled"
        assert captured["project_names"] == ["Agenda"]
        assert captured["limit"] == 50

    def test_events_of_today_forces_timed_items(self, monkeypatch):
        captured = {}

        def fake_query_agenda(**kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

        monkeypatch.setattr(read, "query_agenda", fake_query_agenda)
        read.events_of_today(local_date="2026-03-20", time_from="09:00", time_to="12:00")

        assert captured["timed_only"] is True
        assert captured["time_from"] == "09:00"
        assert captured["time_to"] == "12:00"

    def test_week_agenda_builds_multi_day_window(self, monkeypatch):
        captured = {}

        def fake_query_agenda(**kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

        monkeypatch.setattr(read, "query_agenda", fake_query_agenda)
        read.week_agenda(local_date="2026-03-20", days=7, project_names=["Agenda"])

        assert captured["from_dt"].startswith("2026-03-20T00:00:00")
        assert captured["to_dt"].startswith("2026-03-26T23:59:59")
        assert captured["project_names"] == ["Agenda"]

    def test_upcoming_tasks_delegates_to_query_tasks(self, monkeypatch):
        captured = {}

        def fake_query_tasks(**kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

        monkeypatch.setattr(read, "query_tasks", fake_query_tasks)
        read.upcoming_tasks(local_date="2026-03-20", days=5, min_priority=3)

        assert captured["due_from"].startswith("2026-03-20T00:00:00")
        assert captured["due_to"].startswith("2026-03-24T23:59:59")
        assert captured["min_priority"] == 3

    def test_priority_dashboard_groups_items(self, monkeypatch):
        monkeypatch.setattr(
            read,
            "query_tasks",
            lambda **kwargs: {
                "count": 4,
                "plan": {"source": "all_active_tasks"},
                "items": [
                    {"id": "a", "priority_label": "high"},
                    {"id": "b", "priority_label": "high"},
                    {"id": "c", "priority_label": "medium"},
                    {"id": "d", "priority_label": "none"},
                ],
            },
        )

        result = read.priority_dashboard(project_names=["Alpha"])

        assert result["count"] == 4
        assert result["buckets"]["high"]["count"] == 2
        assert result["buckets"]["medium"]["count"] == 1
        assert result["buckets"]["none"]["count"] == 1
        assert result["scope"]["project_names"] == ["Alpha"]

    def test_week_overview_splits_sections(self, monkeypatch):
        monkeypatch.setattr(read, "week_agenda", lambda **kwargs: {"count": 1, "items": [{"id": "event1"}]})
        monkeypatch.setattr(read, "upcoming_tasks", lambda **kwargs: {"count": 2, "items": [{"id": "due1"}, {"id": "due2"}]})
        monkeypatch.setattr(read, "overdue_tasks", lambda **kwargs: {"count": 1, "items": [{"id": "late1"}]})

        result = read.week_overview(local_date="2026-03-20", days=7)

        assert result["events"]["count"] == 1
        assert result["due_tasks"]["count"] == 2
        assert result["overdue"]["count"] == 1

    def test_query_preset_roundtrip(self, monkeypatch, tmp_path):
        store = read._preset_store()
        monkeypatch.setattr(store, "_base_dir", tmp_path)
        monkeypatch.setattr(store, "_path", tmp_path / "query_presets.json")

        save = read.save_query_preset(
            name="my-week",
            query_type="week_overview",
            filters={"local_date": "2026-03-20", "days": 7},
            description="Weekly planning view",
        )
        listed = read.list_query_presets()
        monkeypatch.setattr(read, "week_overview", lambda **kwargs: {"count": 3, "window": kwargs})
        run = read.run_query_preset("my-week")
        deleted = read.delete_query_preset("my-week")

        assert save["saved"] is True
        assert listed["count"] == 1
        assert run["result"]["count"] == 3
        assert deleted["deleted"] is True


@pytest.mark.unit
class TestVerifiedActions:
    def test_create_subtask_verifies_child_and_parent(self, monkeypatch):
        monkeypatch.setattr(server_mod, "create_task", lambda **kwargs: {"id": "child1", "projectId": "p1", "title": kwargs["title"]})
        monkeypatch.setattr(server_mod, "set_subtask_parent", lambda **kwargs: {"ok": True})
        monkeypatch.setattr(verified.client, "get_task", lambda project_id, task_id: Task(id=task_id, projectId=project_id, title="Child", parentId="parent1"))
        monkeypatch.setattr(
            verified.client,
            "get_project_data",
            lambda project_id: ProjectData(
                project=Project(id=project_id, name="Work"),
                tasks=[Task(id="parent1", projectId=project_id, title="Parent", childIds=["child1"])],
            ),
        )

        result = verified.create_subtask(title="Child", project_id="p1", parent_id="parent1")

        assert result["verified"] is True
        assert result["created"]["parentId"] == "parent1"

    def test_verified_create_project_checks_v1_and_v2(self, monkeypatch):
        monkeypatch.setattr(server_mod, "create_project", lambda **kwargs: {"id": "p1", "name": kwargs["name"], "groupId": kwargs.get("group_id")})
        monkeypatch.setattr(verified.client, "get_project", lambda project_id: Project(id=project_id, name="Alpha"))
        monkeypatch.setattr(
            verified.client,
            "sync_all",
            lambda: SimpleNamespace(projectProfiles=[Project(id="p1", name="Alpha", groupId="g1")]),
        )

        result = verified.verified_create_project(name="Alpha", group_id="g1")

        assert result["verified"] is True
        assert result["verification"]["group_id_persisted_v2"] is True

    def test_verified_move_tasks_checks_destination_presence(self, monkeypatch):
        monkeypatch.setattr(server_mod, "move_tasks", lambda moves: {"result": "ok", "cascaded_children": [{"taskId": "child1", "fromProjectId": "p1", "toProjectId": "p2"}]})
        monkeypatch.setattr(
            verified.client,
            "get_project_data",
            lambda project_id: ProjectData(
                project=Project(id=project_id, name="Dest"),
                tasks=[
                    Task(id="task1", projectId=project_id, title="Moved"),
                    Task(id="child1", projectId=project_id, title="Moved child"),
                ],
            ),
        )

        result = verified.verified_move_tasks([{"taskId": "task1", "fromProjectId": "p1", "toProjectId": "p2"}])

        assert result["verified"] is True
        assert result["verification"][0]["missing_task_ids"] == []

    def test_verified_batch_move_adds_rollback_hint_on_failure(self, monkeypatch):
        monkeypatch.setattr(
            verified,
            "verified_move_tasks",
            lambda moves: {"error": True, "verified": False, "verification": [{"project_id": "p2", "missing_task_ids": ["t1"]}]},
        )

        result = verified.verified_batch_move([{"taskId": "t1", "fromProjectId": "p1", "toProjectId": "p2"}])

        assert result["error"] is True
        assert result["rollback_hint"]["moves"][0]["fromProjectId"] == "p2"
        assert result["rollback_hint"]["moves"][0]["toProjectId"] == "p1"

    def test_verified_assign_project_folder_uses_sync_state(self, monkeypatch):
        sync_states = [
            SimpleNamespace(projectProfiles=[Project(id="p1", name="Alpha", groupId=None)]),
            SimpleNamespace(projectProfiles=[Project(id="p1", name="Alpha", groupId="g1")]),
        ]
        monkeypatch.setattr(verified.client, "sync_all", lambda: sync_states.pop(0))
        monkeypatch.setattr(server_mod, "update_project", lambda **kwargs: {"id": kwargs["project_id"], "groupId": kwargs["group_id"]})

        result = verified.verified_assign_project_folder(project_id="p1", group_id="g1")

        assert result["verified"] is True
        assert result["after"]["groupId"] == "g1"
