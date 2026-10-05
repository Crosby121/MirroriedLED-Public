"""Check ownership, handoff, provenance and privacy boundaries using isolated Git checkouts."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ai_workflow", REPO / "tools/ai_workflow.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class SharedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        shutil.copytree(REPO / "docs/ai-workflow", self.root / workflow.REL)
        shutil.copy2(REPO / "AGENTS.md", self.root / "AGENTS.md")
        (self.root / ".github").mkdir()
        shutil.copy2(REPO / ".github/copilot-instructions.md", self.root / ".github/copilot-instructions.md")
        # Normalize mutable production records into independent lifecycle fixtures.
        queue = workflow.read(self.root / workflow.REL / "tasks.json")
        for task in queue["tasks"]:
            task.update(status="done" if task["id"] == "WF-001" else
                        "blocked" if task["id"] == "WF-002" else "ready",
                        owner_session_id=None)
        workflow.write(self.root / workflow.REL / "tasks.json", queue)
        for path in (self.root / workflow.REL / "sessions").glob("*.json"):
            record = workflow.read(path)
            if record["status"] == "active":
                record.update(status="completed", ended_at=record["started_at"],
                              summary="Fixture foundation completed", next_action="Connect clients")
                workflow.write(path, record)
        workflow.report(self.root)
        workflow.validate(self.root)

    def task(self, task_id):
        queue = workflow.read(self.root / workflow.REL / "tasks.json")
        return next(item for item in queue["tasks"] if item["id"] == task_id)

    def record(self, session_id):
        return workflow.read(self.root / workflow.REL / "sessions" / (session_id + ".json"))

    def test_completed_handoff_releases_task_and_records_declared_identity(self):
        session_id = workflow.start(self.root, "GitHub Copilot", "WF-003", "fixture-user")
        active = self.record(session_id)
        self.assertEqual(active["application_identity"], "declared")
        self.assertEqual(active["github_account"], "fixture-user")
        self.assertEqual(self.task("WF-003")["owner_session_id"], session_id)
        workflow.finish(self.root, session_id, "completed", "Fixture connection checked",
                        "Import the accessible history", ["AGENTS.md"], ["fixture validation command"])
        record = self.record(session_id)
        self.assertEqual(record["status"], "completed")
        self.assertIsNotNone(record["ended_at"])
        self.assertEqual(record["changed_files"], ["AGENTS.md"])
        self.assertEqual(record["checks"][0]["basis"], "agent_report")
        self.assertEqual(self.task("WF-003")["status"], "done")
        self.assertIsNone(self.task("WF-003")["owner_session_id"])
        workflow.validate(self.root)

    def test_blocked_handoff_can_be_taken_over_by_a_new_session(self):
        original = workflow.start(self.root, "ChatGPT Work / Codex", "WF-002")
        workflow.finish(self.root, original, "blocked", "Hosting setting still unavailable",
                        "Resolve the missing setting")
        replacement = workflow.start(self.root, "Hostinger Agent", "WF-002")
        self.assertEqual(self.record(original)["status"], "blocked")
        self.assertEqual(self.task("WF-002")["last_session_id"], original)
        self.assertEqual(self.task("WF-002")["owner_session_id"], replacement)
        workflow.validate(self.root)

    def test_another_session_cannot_claim_an_owned_task(self):
        original = workflow.start(self.root, "Copilot", "WF-003")
        before = json.dumps(self.task("WF-003"), sort_keys=True)
        with self.assertRaisesRegex(ValueError, "already claimed"):
            workflow.start(self.root, "Hostinger Agent", "WF-003")
        self.assertEqual(json.dumps(self.task("WF-003"), sort_keys=True), before)
        self.assertEqual(self.task("WF-003")["owner_session_id"], original)

    def test_a_finished_record_cannot_be_overwritten(self):
        session_id = workflow.start(self.root, "Copilot", "WF-003")
        workflow.finish(self.root, session_id, "blocked", "Unfinished", "Continue later")
        before = self.record(session_id)
        with self.assertRaisesRegex(ValueError, "already finished"):
            workflow.finish(self.root, session_id, "completed", "Rewrite", "Skip")
        self.assertEqual(self.record(session_id), before)

    def test_unknown_task_or_unfinished_dependencies_do_not_create_a_claim(self):
        with self.assertRaisesRegex(ValueError, "Unknown task"):
            workflow.start(self.root, "Copilot", "WF-999")
        queue = workflow.read(self.root / workflow.REL / "tasks.json")
        next(item for item in queue["tasks"] if item["id"] == "WF-001").update(
            status="blocked", next_action="Fixture prerequisite missing")
        workflow.write(self.root / workflow.REL / "tasks.json", queue)
        workflow.report(self.root)
        with self.assertRaisesRegex(ValueError, "dependencies are unfinished"):
            workflow.start(self.root, "Copilot", "WF-003")
        self.assertIsNone(self.task("WF-003")["owner_session_id"])

    def test_local_lock_prevents_overlapping_helper_writes(self):
        lock = self.root / ".git/mirroriedled-ai-workflow.lock"
        lock.mkdir()
        with self.assertRaisesRegex(ValueError, "local write lock"):
            workflow.start(self.root, "Copilot", "WF-003")
        self.assertIsNone(self.task("WF-003")["owner_session_id"])

    def test_unsafe_session_and_file_paths_are_rejected_without_writing(self):
        with self.assertRaisesRegex(ValueError, "Invalid session ID"):
            workflow.finish(self.root, "../state", "completed", "Bad path", "Stop")
        session_id = workflow.start(self.root, "Copilot", "WF-003")
        for name in ("../config.php", "/absolute/file", "C:/private/key", "folder\\file"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "repository-relative"):
                workflow.finish(self.root, session_id, "completed", "Bad path", "Stop", [name])
        self.assertEqual(self.record(session_id)["status"], "active")

    def test_stale_readable_status_is_detected_and_can_be_regenerated(self):
        queue = workflow.read(self.root / workflow.REL / "tasks.json")
        next(item for item in queue["tasks"] if item["id"] == "WF-002")["next_action"] = "New observed next action"
        workflow.write(self.root / workflow.REL / "tasks.json", queue)
        with self.assertRaisesRegex(ValueError, "stale"):
            workflow.validate(self.root)
        workflow.report(self.root)
        workflow.validate(self.root)

    def test_source_success_does_not_supply_missing_live_deployment_evidence(self):
        path = self.root / workflow.REL / "state.json"
        state = workflow.read(path)
        # This case requires missing live evidence regardless of the production snapshot.
        state["deployment"].update(live_commit=None, live_verified_at=None,
                                   verification_evidence=[])
        self.assertIsNone(state["deployment"]["live_commit"])
        state["deployment"]["live_commit"] = state["source"]["observed_commit"]
        workflow.write(path, state)
        with self.assertRaisesRegex(ValueError, "Timestamp"):
            workflow.validate(self.root)
        state["deployment"]["live_verified_at"] = state["observed_at"]
        workflow.write(path, state)
        with self.assertRaisesRegex(ValueError, "verification evidence"):
            workflow.validate(self.root)

    def test_imported_ai_attribution_stays_unknown(self):
        path = self.root / workflow.REL / "history/github-baseline.json"
        history = workflow.read(path)
        history["events"][0]["application"] = "An inferred AI app"
        workflow.write(path, history)
        with self.assertRaisesRegex(ValueError, "attribution must remain unknown"):
            workflow.validate(self.root)

    def test_broken_ownership_and_dependency_cycles_are_detected(self):
        path = self.root / workflow.REL / "tasks.json"
        queue = workflow.read(path)
        connection = next(item for item in queue["tasks"] if item["id"] == "WF-003")
        history = next(item for item in queue["tasks"] if item["id"] == "WF-004")
        connection.update(status="in_progress", owner_session_id="missing-session")
        workflow.write(path, queue)
        workflow.report(self.root)
        with self.assertRaisesRegex(ValueError, "active recorded session"):
            workflow.validate(self.root)
        connection.update(status="ready", owner_session_id=None, depends_on=["WF-004"])
        history["depends_on"] = ["WF-003"]
        workflow.write(path, queue)
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            workflow.validate(self.root)

    def test_credential_value_is_rejected_before_handoff_writes(self):
        session_id = workflow.start(self.root, "Copilot", "WF-003")
        for prefix in ("ghp_", "github_pat_", "sk-proj-", "sk-"):
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, "Credentials cannot be recorded"):
                workflow.finish(self.root, session_id, "blocked", prefix + "X" * 36, "Continue")
            self.assertEqual(self.record(session_id)["status"], "active")

    def test_shared_record_credential_scan_reports_only_the_filename(self):
        path = self.root / workflow.REL / "state.json"
        state = workflow.read(path)
        for prefix in ("ghp_", "github_pat_", "sk-proj-", "sk-"):
            token = prefix + "X" * 36
            state["limitations"].append(token)
            workflow.write(path, state)
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, "Potential credential in state.json") as failure:
                workflow.validate(self.root, check_report=False)
            self.assertNotIn(token, str(failure.exception))
            state["limitations"].pop()


if __name__ == "__main__":
    unittest.main()
