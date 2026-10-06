"""Exercise the real PHP MCP handler against a deterministic GitHub HTTP double."""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import uuid


ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get("PHP_BIN") or shutil.which("php")
PREFIX = "docs/ai-workflow/"
TOKEN_A = "mlwf_" + "A" * 64
TOKEN_B = "mlwf_" + "B" * 64


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load_module("workflow_test_helper", ROOT / "tools/ai_workflow.py")
configure = load_module("workflow_test_config", ROOT / "tools/configure_ai_workflow.py")


class GitHubDouble:
    def __init__(self):
        self.lock = threading.RLock()
        self.barrier = None
        self.barrier_count = 0
        self.ref_writes = []
        self.drop_after_write = False
        self.reject_ref = False
        self.account = "Crosby121"
        files = {str(path.relative_to(ROOT)): path.read_text() for path in (ROOT / PREFIX).rglob("*") if path.is_file()}
        for path in ["AGENTS.md", ".github/copilot-instructions.md"]:
            files[path] = (ROOT / path).read_text()
        files["index.html"] = "Existing website content must be preserved."
        queue = json.loads(files[PREFIX + "tasks.json"])
        for task in queue["tasks"]:
            task.update(owner_session_id=None, last_session_id=None,
                        status="done" if task["id"] in {"WF-001", "WF-005"} else "ready")
        for path in files:
            if path.startswith(PREFIX + "sessions/"):
                session = json.loads(files[path])
                if session["status"] == "active":
                    session.update(status="blocked", ended_at=session["started_at"], summary="Fixture closed session", next_action="Continue in fixture")
                files[path] = json.dumps(session)
        files[PREFIX + "tasks.json"] = json.dumps(queue)
        files[PREFIX + "CURRENT_STATUS.md"] = helper.render(json.loads(files[PREFIX + "state.json"]), queue)
        self.head = "1" * 40
        self.commits = {self.head: {"files": files, "parents": [], "tree": "2" * 40}}
        self.trees = {"2" * 40: files}

    @staticmethod
    def sha():
        return hashlib.sha1(uuid.uuid4().bytes).hexdigest()

    def request(self, method, url, body):
        parsed = urlparse(url)
        path = parsed.path.removeprefix("/repos/Crosby121/MirroriedLED-Public/")
        if path == "git/ref/heads/main" and method == "GET":
            with self.lock:
                head = self.head
                barrier = self.barrier if self.barrier_count < 2 else None
                if barrier is not None:
                    self.barrier_count += 1
            if barrier is not None:
                barrier.wait(timeout=8)
            return 200, {"object": {"sha": head}}
        with self.lock:
            if parsed.path == "/user":
                return 200, {"login": self.account}
            if path.startswith("contents/") and method == "GET":
                head = parse_qs(parsed.query)["ref"][0]
                text = self.commits[head]["files"][path[len("contents/"):]]
                return 200, {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}
            if path.startswith("git/trees/") and method == "GET":
                files = self.commits[path[len("git/trees/"):]]["files"]
                return 200, {"truncated": False, "tree": [{"path": p, "mode": "100644", "type": "blob"} for p in files]}
            if path.startswith("git/commits/") and method == "GET":
                return 200, {"tree": {"sha": self.commits[path[len("git/commits/"):]]["tree"]}}
            if path == "git/trees" and method == "POST":
                files = self.trees[body["base_tree"]].copy()
                for entry in body["tree"]:
                    files[entry["path"]] = entry["content"]
                sha = self.sha()
                self.trees[sha] = files
                return 201, {"sha": sha}
            if path == "git/commits" and method == "POST":
                sha = self.sha()
                self.commits[sha] = {"files": self.trees[body["tree"]], "tree": body["tree"], "parents": body["parents"]}
                return 201, {"sha": sha}
            if path == "git/refs/heads/main" and method == "PATCH":
                self.ref_writes.append(body)
                if self.reject_ref or body.get("force") is not False or self.head not in self.commits[body["sha"]]["parents"]:
                    return 409, {"message": "Update rejected"}
                self.head = body["sha"]
                if self.drop_after_write:
                    self.drop_after_write = False
                    return 503, {"message": "Response lost after commit"}
                return 200, {"object": {"sha": self.head}}
            return 404, {"message": "Unknown endpoint"}

    def add_unrelated_commit(self):
        with self.lock:
            files = self.commits[self.head]["files"].copy()
            files["another-app.txt"] = "Another app's change"
            sha, tree = self.sha(), self.sha()
            self.trees[tree] = files
            self.commits[sha] = {"files": files, "tree": tree, "parents": [self.head]}
            self.head = sha


@unittest.skipUnless(PHP, "PHP 8.2+ with cURL is required")
class WorkflowMCPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.github = GitHubDouble()
        github = self.github

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length)) if length else None
                try:
                    status, data = github.request(self.command, self.path, body)
                except Exception:
                    status, data = 500, {"error": "GitHub double failed"}
                content = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            do_GET = do_POST = do_PATCH = handle_request

        self.github_http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.github_http.serve_forever, daemon=True)
        self.thread.start()
        config = {"repository": "Crosby121/MirroriedLED-Public", "branch": "main", "expected_github_account": "Crosby121",
                  "github_token": "test-service-credential-" + "X" * 40,
                  "allowed_origins": ["https://mirroriedled.com"],
                  "clients": {"copilot": {"application": "GitHub Copilot", "token_sha256": hashlib.sha256(TOKEN_A.encode()).hexdigest()},
                              "hostinger-agent": {"application": "Hostinger Agent", "token_sha256": hashlib.sha256(TOKEN_B.encode()).hexdigest()}}}
        self.config_path = self.directory / "config.json"
        self.config_path.write_text(json.dumps(config))
        environment = os.environ.copy()
        environment.pop("PHP_CLI_SERVER_WORKERS", None)
        environment.update(WF_TEST_CONFIG=str(self.config_path), WF_TEST_GITHUB=f"http://127.0.0.1:{self.github_http.server_port}")
        self.logs = (self.directory / "php.log").open("w")
        self.processes, self.urls = [], {}
        # Separate listeners guarantee overlap. A shared CLI worker listener can
        # schedule both requests on one process and deadlock the test barrier.
        for token in [TOKEN_A, TOKEN_B]:
            with socket.socket() as free_port:
                free_port.bind(("127.0.0.1", 0))
                port = free_port.getsockname()[1]
            self.urls[token] = f"http://127.0.0.1:{port}/mcp"
            process = subprocess.Popen([PHP, "-S", f"127.0.0.1:{port}", str(ROOT / "tests/fixtures/ai-workflow-router.php")],
                                       env=environment, stdout=self.logs, stderr=self.logs, start_new_session=True)
            self.processes.append(process)
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    if process.poll() is not None:
                        self.fail("PHP integration server failed to start")
                    time.sleep(0.01)
            else:
                self.fail("PHP integration server did not start")

    def tearDown(self):
        for process in self.processes:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        self.logs.close()
        self.github_http.shutdown()
        self.github_http.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def rpc(self, name=None, args=None, token=TOKEN_A, method="tools/call", headers=None, payload=None, http_method="POST"):
        request_headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json",
                           "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
        request_headers.update(headers or {})
        message = payload or {"jsonrpc": "2.0", "id": 1, "method": method,
                              "params": {"name": name, "arguments": args or {}}}
        data = json.dumps(message).encode() if http_method == "POST" else None
        try:
            response = urlopen(Request(self.urls.get(token, self.urls[TOKEN_A]), data=data, method=http_method, headers=request_headers), timeout=20)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None

    def call(self, name, args=None, token=TOKEN_A):
        status, response = self.rpc(name, args, token)
        self.assertEqual(status, 200, response)
        self.assertIn("result", response, response)
        return response["result"]

    def start(self, task="WF-003", token=TOKEN_A, request_id=None):
        application = "GitHub Copilot" if token == TOKEN_A else "Hostinger Agent"
        return self.call("start_session", {"request_id": request_id or uuid.uuid4().hex, "application": application,
                                         "task_id": task, "branch": "work/example", "base_commit": "1" * 40}, token)

    @staticmethod
    def handoff(session, outcome="completed"):
        return {"session_id": session, "outcome": outcome, "summary": "Fixed the task and checked the result.",
                "next_action": "Continue with the next ready task.", "changed_files": ["tools/example.py"],
                "checks": [{"name": "Actual fixture check", "result": "passed", "command": "fixture-check"}],
                "evidence_urls": ["https://github.com/Crosby121/MirroriedLED-Public/pull/13"]}

    def assert_valid_published_records(self):
        root = self.directory / "readback"
        for path, text in self.github.commits[self.github.head]["files"].items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        helper.validate(root)
        self.assertEqual((root / "index.html").read_text(), "Existing website content must be preserved.")
        self.assertTrue(all(write["force"] is False for write in self.github.ref_writes))

    def test_auth_origin_and_transport_reject_before_github_access(self):
        initial = self.github.head
        for headers, token, expected in [({}, "invalid", 401), ({"Origin": "https://evil.example"}, TOKEN_A, 403),
                                         ({"MCP-Protocol-Version": "unknown"}, TOKEN_A, 400),
                                         ({"Content-Type": "text/plain"}, TOKEN_A, 415), ({"Accept": "application/json"}, TOKEN_A, 406)]:
            with self.subTest(headers=headers):
                self.assertEqual(self.rpc("read_state", token=token, headers=headers)[0], expected)
        self.assertEqual(self.rpc(token=TOKEN_A, http_method="GET")[0], 405)
        self.assertEqual(self.github.head, initial)

    def test_protocol_negotiation_notifications_and_real_tool_discovery(self):
        status, result = self.rpc(method="initialize", payload={"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2026-07-28"}})
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("before editing", result["result"]["instructions"])
        self.assertEqual(self.rpc(payload={"jsonrpc": "2.0", "method": "notifications/initialized"}), (202, None))
        _, result = self.rpc(method="tools/list")
        self.assertEqual({x["name"] for x in result["result"]["tools"]}, {"read_state", "read_history", "start_session", "claim_task", "finish_session"})
        self.assertEqual(self.rpc(payload=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}])[0], 400)

    def test_session_round_trip_replays_and_publishes_valid_handoff(self):
        started = self.start(request_id="same-request-123")
        self.assertFalse(started["isError"], started)
        session = started["structuredContent"]["session"]["id"]
        head = self.github.head
        replay = self.start(request_id="same-request-123")
        self.assertTrue(replay["structuredContent"]["replayed"])
        self.assertEqual(self.github.head, head)
        handoff = self.handoff(session)
        finished = self.call("finish_session", handoff)
        self.assertFalse(finished["isError"], finished)
        head = self.github.head
        self.assertTrue(self.call("finish_session", handoff)["structuredContent"]["replayed"])
        self.assertEqual(self.github.head, head)
        handoff["summary"] = "Cannot rewrite a completed handoff"
        self.assertEqual(self.call("finish_session", handoff)["structuredContent"]["error"]["code"], "session_closed")
        state = self.call("read_state")["structuredContent"]
        self.assertEqual(state["service_github_account"], "Crosby121")
        self.assertEqual(state["recent_task_sessions"][0]["id"], session)
        self.assert_valid_published_records()

    def test_actual_concurrent_clients_cannot_claim_the_same_task(self):
        self.github.barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda token: self.start(token=token), [TOKEN_A, TOKEN_B]))
        self.assertEqual(sum(not result["isError"] for result in results), 1, results)
        rejected = next(result for result in results if result["isError"])
        self.assertEqual(rejected["structuredContent"]["error"]["code"], "task_conflict")
        self.assert_valid_published_records()

    def test_concurrent_independent_claims_preserve_both_records_and_unrelated_work(self):
        self.github.add_unrelated_commit()
        self.github.barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.start, "WF-003", TOKEN_A), executor.submit(self.start, "WF-004", TOKEN_B)]
            results = [future.result() for future in futures]
        self.assertTrue(all(not result["isError"] for result in results), results)
        self.assertEqual(self.github.commits[self.github.head]["files"]["another-app.txt"], "Another app's change")
        self.assert_valid_published_records()

    def test_lost_response_retry_does_not_duplicate_a_start(self):
        self.github.drop_after_write = True
        first = self.start(request_id="lost-response-123")
        self.assertTrue(first["isError"])
        head = self.github.head
        retried = self.start(request_id="lost-response-123")
        self.assertFalse(retried["isError"], retried)
        self.assertTrue(retried["structuredContent"]["replayed"])
        self.assertEqual(self.github.head, head)

    def test_unknown_tasks_dependencies_and_request_id_reuse_do_not_publish(self):
        initial = self.github.head
        self.assertEqual(self.start(task="WF-999")["structuredContent"]["error"]["code"], "unknown_task")
        self.assertEqual(self.github.head, initial)
        self.assertFalse(self.start(request_id="reuse-once-123")["isError"])
        initial = self.github.head
        reused = self.start(task="WF-004", request_id="reuse-once-123")
        self.assertEqual(reused["structuredContent"]["error"]["code"], "idempotency_conflict")
        self.assertEqual(self.github.head, initial)

    def test_other_app_cannot_finish_or_extend_a_session(self):
        session = self.start()["structuredContent"]["session"]["id"]
        initial = self.github.head
        for name, args in [("finish_session", self.handoff(session)), ("claim_task", {"session_id": session, "task_id": "WF-004"})]:
            result = self.call(name, args, TOKEN_B)
            self.assertEqual(result["structuredContent"]["error"]["code"], "session_owner")
        self.assertEqual(self.github.head, initial)

    def test_tokenized_evidence_is_rejected_and_standard_github_comments_are_allowed(self):
        session = self.start()["structuredContent"]["session"]["id"]
        initial = self.github.head
        for url in ['https://example.test/proof?token=opaque-credential', 'https://example.test/proof#opaque-credential',
                    'https://github.com/Crosby121/MirroriedLED-Public/pull/13?signature=opaque']:
            handoff = self.handoff(session)
            handoff['evidence_urls'] = [url]
            self.assertTrue(self.call('finish_session', handoff)['isError'])
            self.assertEqual(self.github.head, initial)
        handoff = self.handoff(session)
        handoff['evidence_urls'] = ['https://github.com/Crosby121/MirroriedLED-Public/pull/13#discussion_r4179712048']
        self.assertFalse(self.call('finish_session', handoff)['isError'])
        self.assert_valid_published_records()

    def test_blocked_handoff_releases_all_tasks_for_a_new_app(self):
        session = self.start()["structuredContent"]["session"]["id"]
        self.assertFalse(self.call("claim_task", {"session_id": session, "task_id": "WF-004"})["isError"])
        self.assertFalse(self.call("finish_session", self.handoff(session, "blocked"))["isError"])
        self.assertFalse(self.start(token=TOKEN_B)["isError"])
        self.assert_valid_published_records()

    def test_secrets_bad_paths_identity_and_unknown_fields_do_not_publish(self):
        session = self.start()["structuredContent"]["session"]["id"]
        initial = self.github.head
        for change in [{"summary": "github_pat_" + "X" * 55}, {"summary": TOKEN_A}, {"changed_files": ["../private"]},
                       {"changed_files": ["C:\\private"]}, {"evidence_urls": ["https://user:password@example.com/proof"]},
                       {"checks": [{"name": "fake", "result": "passed", "extra": "unsupported"}]}, {"extra": "unsupported"}]:
            args = self.handoff(session)
            args.update(change)
            self.assertTrue(self.call("finish_session", args)["isError"], change)
        start_args = {"request_id": "different-app-123", "application": "Hostinger Agent", "task_id": "WF-004", "branch": "work/test", "base_commit": "1" * 40}
        self.assertTrue(self.call("start_session", start_args)["isError"])
        self.assertTrue(self.call("read_state", {"extra": "unsupported"})["isError"])
        self.assertEqual(self.github.head, initial)

    def test_service_account_and_ref_rules_fail_closed(self):
        initial = self.github.head
        self.github.account = "SomebodyElse"
        self.assertEqual(self.start()["structuredContent"]["error"]["code"], "github_identity")
        self.github.account = "Crosby121"
        self.github.reject_ref = True
        self.assertEqual(self.start()["structuredContent"]["error"]["code"], "github_access")
        self.assertEqual(self.github.head, initial)

    def test_history_is_paginated_and_preserves_unknown_attribution(self):
        self.start()
        first = self.call("read_history", {"limit": 1})["structuredContent"]
        self.assertEqual(len(first["sessions"]), 1)
        self.assertIsNotNone(first["next_cursor"])
        second = self.call("read_history", {"limit": 1, "cursor": first["next_cursor"]})["structuredContent"]
        self.assertNotEqual(first["sessions"][0]["id"], second["sessions"][0]["id"])
        for event in first["github_baseline"]["events"]:
            self.assertIsNone(event.get("application"))


class PrivateConfigurationTests(unittest.TestCase):
    def test_generator_keeps_plain_credentials_private_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "private"
            config = configure.create_config(directory, "fixture-GitHub-token-" + "A" * 40)
            credentials = json.loads((directory / "client-credentials.json").read_text())
            self.assertEqual(len(set(credentials.values())), 3)
            for app, token in credentials.items():
                self.assertEqual(config["clients"][app]["token_sha256"], hashlib.sha256(token.encode()).hexdigest())
                self.assertNotIn(token, (directory / "config.json").read_text())
            self.assertEqual((directory / "config.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                configure.create_config(directory, "another-fixture-GitHub-token-" + "B" * 40)


if __name__ == "__main__":
    unittest.main()
