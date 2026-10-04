#!/usr/bin/env python3
"""Read and maintain the shared AI work record. No network or deployment actions."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
REL = Path("docs/ai-workflow")
SESSION_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,95}")
TASK_ID = re.compile(r"WF-[0-9]{3,}")
COMMIT = re.compile(r"[0-9a-f]{40}")
SECRET = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,}")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value):
    require(isinstance(value, str) and value.endswith("Z"), "Timestamp must be UTC and end in Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    require(parsed.utcoffset().total_seconds() == 0, "Timestamp must use UTC")
    return parsed


def read(path):
    require(path.is_file() and not path.is_symlink(), f"Missing or unsafe record: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.is_symlink(), f"Refusing symlink: {path.name}")
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def git(root, *arguments):
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


@contextmanager
def locked(root):
    location = git(root, "rev-parse", "--git-path", "mirroriedled-ai-workflow.lock")
    require(location, "Session logging requires a Git checkout")
    lock = Path(location)
    if not lock.is_absolute():
        lock = root / lock
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError("Another helper owns the local write lock; check for an active writer before removing a stale lock")
    try:
        yield
    finally:
        lock.rmdir()


def cell(value):
    return str(value).replace("|", r"\|").replace("\n", " ")


def render(state, queue):
    repository, source, deployment = state["repository"], state["source"], state["deployment"]
    attempt = deployment["last_attempt"]
    lines = [
        "# Mirroried LED shared work status", "",
        f"Evidence snapshot: {state['observed_at']} (UTC). Refresh GitHub at the start of each session.",
        "",
        "| Area | Recorded state |",
        "| --- | --- |",
        f"| Repository | [{repository['full_name']}]({repository['url']}) · {repository['default_branch']} |",
        f"| Observed website source | [{source['observed_commit'][:7]}]({source['evidence_url']}) · {cell(source['summary'])} |",
        f"| Verified live Hostinger commit | {deployment['live_commit'] or 'Unknown — no verified live commit recorded'} |",
        f"| Last Hostinger attempt | [{cell(attempt['status'])}]({attempt['evidence_url']}) · {cell(attempt['failed_step'])} |",
        f"| Deployment blocker | {cell(attempt['finding'])} |",
        "| Shared app connections | Instructions and local logger available; common remote connector is queued |",
        "", "## Source checks", "",
    ]
    for check in source["checks"]:
        lines.append(f"- [{cell(check['name'])}]({check['evidence_url']}): **{check['result']}**.")
    lines += ["", "## Task queue", "", "| Task | Status | Owner session | Next action |",
              "| --- | --- | --- | --- |"]
    for task in sorted(queue["tasks"], key=lambda item: (item["priority"], item["id"])):
        lines.append(f"| {task['id']} — {cell(task['title'])} | {task['status']} | {task['owner_session_id'] or 'Unclaimed'} | {cell(task['next_action'])} |")
    lines += ["", "## Continue", "",
              f"First operational task: **{state['next_task_id']}**. Independent ready tasks may proceed after checking ownership.",
              "", "Read [the workflow guide](README.md), the actual GitHub HEAD and open PRs, and the relevant feature/release docs.",
              "See [session records](sessions/) and [imported GitHub evidence](history/github-baseline.json).",
              "", "This record does not grant account access or capture all chats automatically. Older AI identities remain unknown.",
              "A green source check or GitHub Pages deployment does not establish the live PHP website's version.", ""]
    return "\n".join(lines)


def report(root, state=None, queue=None):
    folder = root / REL
    state = state or read(folder / "state.json")
    queue = queue or read(folder / "tasks.json")
    target = folder / "CURRENT_STATUS.md"
    require(not target.is_symlink(), "Refusing symlinked status report")
    target.write_text(render(state, queue), encoding="utf-8")


def validate(root, check_report=True):
    folder = root / REL
    require(not (root / "docs").is_symlink() and not folder.is_symlink()
            and not (folder / "sessions").is_symlink()
            and not (folder / "history").is_symlink(), "Workflow folders must not be symlinks")
    state, queue = read(folder / "state.json"), read(folder / "tasks.json")
    require(state["schema_version"] == queue["schema_version"] == 1, "Unsupported record version")
    timestamp(state["observed_at"])
    timestamp(queue["updated_at"])
    require(COMMIT.fullmatch(state["source"]["observed_commit"]), "Invalid source commit")
    deployment = state["deployment"]
    if deployment["live_commit"] is not None:
        require(COMMIT.fullmatch(deployment["live_commit"]), "Invalid live commit")
        timestamp(deployment["live_verified_at"])
        require(deployment["verification_evidence"], "A live commit requires verification evidence")
    require(isinstance(queue["tasks"], list), "Tasks must be an array")
    tasks = {}
    for task in queue["tasks"]:
        require(TASK_ID.fullmatch(task["id"]), "Invalid task ID")
        require(task["id"] not in tasks, f"Duplicate task: {task['id']}")
        require(task["status"] in {"ready", "in_progress", "blocked", "done"}, "Invalid task status")
        require(isinstance(task["priority"], int) and task["priority"] > 0, "Invalid priority")
        require(task["title"] and task["next_action"], "Task needs title and next action")
        for key in ("depends_on", "acceptance", "evidence"):
            require(isinstance(task[key], list), f"Task {key} must be an array")
        tasks[task["id"]] = task
    require(state["next_task_id"] in tasks, "Next task does not exist")
    for task in tasks.values():
        require(all(item in tasks for item in task["depends_on"]), "Unknown dependency")
    def visit(task_id, trail):
        require(task_id not in trail, "Task dependency cycle")
        for dependency in tasks[task_id]["depends_on"]:
            visit(dependency, trail | {task_id})
    for task_id in tasks:
        visit(task_id, set())
    sessions = {}
    for path in sorted((folder / "sessions").glob("*.json")):
        session = read(path)
        require(session["schema_version"] == 1, "Unsupported session version")
        require(SESSION_ID.fullmatch(session["id"]), "Invalid session ID")
        require(path.stem == session["id"], "Session filename and ID disagree")
        require(session["status"] in {"active", "completed", "blocked"}, "Invalid session status")
        require(session["application"] and session["application_identity"] == "declared", "Application declaration is required")
        started = timestamp(session["started_at"])
        if session["status"] == "active":
            require(session["ended_at"] is None, "Active session cannot have an end time")
        else:
            require(timestamp(session["ended_at"]) >= started, "Session ends before it starts")
            require(session["summary"] and session["next_action"], "Ended session requires a handoff")
        require(session["base_commit"] is None or COMMIT.fullmatch(session["base_commit"]), "Invalid base commit")
        require(isinstance(session["task_ids"], list) and session["task_ids"], "Session needs task IDs")
        require(all(task_id in tasks for task_id in session["task_ids"]), "Session references an unknown task")
        require(isinstance(session["changed_files"], list) and isinstance(session["checks"], list), "Invalid session arrays")
        for name in session["changed_files"]:
            require(isinstance(name, str) and name and not PurePosixPath(name).is_absolute()
                    and ".." not in PurePosixPath(name).parts and "\\" not in name
                    and ":" not in name, "Changed files must be repository-relative")
        for check in session["checks"]:
            require(check["name"] and check["result"] in {"passed", "failed", "skipped", "not_run"}, "Invalid check record")
        sessions[session["id"]] = session
    for task in tasks.values():
        owner = task["owner_session_id"]
        if task["status"] == "in_progress":
            require(owner in sessions and sessions[owner]["status"] == "active", "Task owner must be an active recorded session")
            require(task["id"] in sessions[owner]["task_ids"], "Owner session does not claim this task")
        else:
            require(owner is None, "Only in-progress tasks may have an owner")
        if task["last_session_id"] is not None:
            require(task["last_session_id"] in sessions, "Unknown previous session")
    for session in sessions.values():
        if session["status"] == "active":
            require(all(tasks[item]["owner_session_id"] == session["id"] for item in session["task_ids"]), "Active session is missing its task claim")
    history = read(folder / "history/github-baseline.json")
    require(history["schema_version"] == 1 and isinstance(history["events"], list), "Invalid imported history")
    timestamp(history["imported_at"])
    for event in history["events"]:
        require(event["evidence_url"] and event["application"] is None, "Baseline AI attribution must remain unknown")
    for path in list(folder.rglob("*.json")) + list(folder.rglob("*.md")) + [root / "AGENTS.md", root / ".github/copilot-instructions.md"]:
        require(not path.is_symlink(), "Shared records must not be symlinks")
        require(not SECRET.search(path.read_text(encoding="utf-8")), f"Potential credential in {path.name}; remove the value")
    if check_report:
        require(readable_text(folder / "CURRENT_STATUS.md") == render(state, queue), "CURRENT_STATUS.md is stale; run status --write")
    return state, queue, sessions


def readable_text(path):
    require(path.is_file() and not path.is_symlink(), "Missing or unsafe status report")
    return path.read_text(encoding="utf-8")


def start(root, application, task_id, account=None):
    require(application and application.strip(), "Application name is required")
    require(not SECRET.search(application + (account or "")), "Credentials cannot be recorded")
    with locked(root):
        state, queue, sessions = validate(root)
        task = next((item for item in queue["tasks"] if item["id"] == task_id), None)
        require(task is not None, "Unknown task")
        require(task["status"] in {"ready", "blocked"} and task["owner_session_id"] is None, "Task is completed or already claimed")
        completed = {item["id"] for item in queue["tasks"] if item["status"] == "done"}
        require(all(item in completed for item in task["depends_on"]), "Task dependencies are unfinished")
        instant = now()
        session_id = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz") + "-" + uuid.uuid4().hex[:8]
        session = {
            "schema_version": 1, "id": session_id, "application": application.strip(),
            "application_identity": "declared", "github_account": account,
            "started_at": instant, "ended_at": None, "status": "active",
            "task_ids": [task_id], "branch": git(root, "branch", "--show-current") or "unknown",
            "base_commit": git(root, "rev-parse", "HEAD"), "summary": "", "next_action": "",
            "changed_files": [], "checks": [], "findings": []
        }
        target = root / REL / "sessions" / (session_id + ".json")
        require(not target.exists(), "Session already exists")
        write(target, session)
        task.update(status="in_progress", owner_session_id=session_id)
        queue["updated_at"] = instant
        write(root / REL / "tasks.json", queue)
        report(root, state, queue)
        validate(root)
        return session_id


def finish(root, session_id, outcome, summary, next_action, files=(), passed_checks=()):
    require(SESSION_ID.fullmatch(session_id), "Invalid session ID")
    require(outcome in {"completed", "blocked"} and summary.strip() and next_action.strip(), "Outcome, summary and next action are required")
    require(all(command.strip() for command in passed_checks), "Check commands must not be empty")
    require(not SECRET.search(json.dumps([summary, next_action, list(files), list(passed_checks)])), "Credentials cannot be recorded")
    for name in files:
        require(name and not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts
                and "\\" not in name and ":" not in name, "Changed files must be repository-relative")
    with locked(root):
        state, queue, sessions = validate(root)
        require(session_id in sessions and sessions[session_id]["status"] == "active", "Session is unknown or already finished")
        session = sessions[session_id]
        session.update(status=outcome, ended_at=now(), summary=summary.strip(),
                       next_action=next_action.strip(), changed_files=sorted(set(files)))
        session["checks"] += [{"name": command, "command": command, "result": "passed", "basis": "agent_report"}
                              for command in passed_checks]
        for task in queue["tasks"]:
            if task["id"] in session["task_ids"]:
                require(task["owner_session_id"] == session_id, "Session no longer owns its task")
                task.update(status="done" if outcome == "completed" else "blocked",
                            owner_session_id=None, last_session_id=session_id, next_action=next_action.strip())
        write(root / REL / "sessions" / (session_id + ".json"), session)
        queue["updated_at"] = session["ended_at"]
        write(root / REL / "tasks.json", queue)
        report(root, state, queue)
        validate(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--write", action="store_true")
    commands.add_parser("validate")
    begin = commands.add_parser("start")
    begin.add_argument("--app", required=True)
    begin.add_argument("--task", required=True)
    begin.add_argument("--github-account")
    end = commands.add_parser("finish")
    end.add_argument("--session", required=True)
    end.add_argument("--outcome", choices=["completed", "blocked"], required=True)
    end.add_argument("--summary", required=True)
    end.add_argument("--next-action", required=True)
    end.add_argument("--changed-file", action="append", default=[])
    end.add_argument("--passed-check", action="append", default=[])
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "status":
            if args.write:
                with locked(root):
                    state, queue, _ = validate(root, check_report=False)
                    report(root, state, queue)
                print("Updated docs/ai-workflow/CURRENT_STATUS.md")
            else:
                state, queue, _ = validate(root, check_report=False)
                print(render(state, queue))
                head = git(root, "rev-parse", "HEAD")
                print(f"Local HEAD: {head or 'unavailable'}")
                if head != state["source"]["observed_commit"]:
                    print("Local HEAD differs from the evidence snapshot; refresh GitHub before implementation.")
        elif args.command == "validate":
            _, queue, sessions = validate(root)
            print(f"WORKFLOW_VALID: {len(queue['tasks'])} tasks, {len(sessions)} sessions")
        elif args.command == "start":
            print("SESSION_ID=" + start(root, args.app, args.task, args.github_account))
            print("Publish the claim and check shared ownership before coding; this is a local reservation.")
        else:
            finish(root, args.session, args.outcome, args.summary, args.next_action, args.changed_file, args.passed_check)
            print("Recorded handoff; commit and push the session, queue and generated status.")
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"WORKFLOW_ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
