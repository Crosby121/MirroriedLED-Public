"""Capture retention, privacy, close recovery, immutable uploads and native framing."""

import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("capture", ROOT / "tools/ai_capture.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class ArchiveDouble:
    def __init__(self, private=True, fail=False):
        self.private = private
        self.fail = fail
        self.files = {}
        self.verifications = 0

    def verify(self):
        self.verifications += 1
        if not self.private:
            raise ValueError("Public repositories cannot receive chat transcripts")

    def put(self, path, data):
        if self.fail:
            raise OSError("Offline")
        if path in self.files and self.files[path] != data:
            raise ValueError("Immutable record conflict")
        self.files[path] = data
        return "https://github.com/" + capture.REPOSITORY + "/blob/main/" + path


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.transcripts = self.root / "native-transcripts"
        self.transcripts.mkdir()
        self.config = {"repository": capture.REPOSITORY, "github_token": "fixture-token-" + "A" * 40,
                       "workspace": str(self.root), "spool": str(self.root / "private/spool"), "transcript_roots": [str(self.transcripts)]}
        self.transcript = self.transcripts / "chat.jsonl"
        self.transcript.write_text('{"role":"user","text":"Mirroried LED task"}\n')

    def event(self, name="Stop"):
        return {"hook_event_name": name, "session_id": "native-session-1", "cwd": str(self.root), "transcript_path": str(self.transcript)}

    def pending(self):
        return list((Path(self.config["spool"]) / "outbox").glob("*.json"))

    def test_complete_available_transcript_and_payload_are_saved_then_receipted(self):
        event = self.event()
        event["last_assistant_message"] = "Completed the task"
        record_id = capture.capture(self.config, event, "copilot")
        record = json.loads(self.pending()[0].read_text())
        self.assertEqual(record["payload"]["last_assistant_message"], "Completed the task")
        self.assertEqual(record["application"], "GitHub Copilot")
        archive = ArchiveDouble()
        self.assertEqual(capture.flush(self.config, archive), 1)
        self.assertFalse(self.pending())
        self.assertEqual(archive.verifications, 1)
        self.assertIn(self.transcript.read_bytes(), archive.files.values())
        self.assertTrue((Path(self.config["spool"]) / "uploaded" / (record_id + ".json")).exists())

    def test_offline_or_public_destination_retains_every_pending_checkpoint(self):
        capture.capture(self.config, self.event(), "codex")
        original = self.pending()[0].read_bytes()
        for archive in [ArchiveDouble(fail=True), ArchiveDouble(private=False)]:
            with self.assertRaises((ValueError, OSError)):
                capture.flush(self.config, archive)
            self.assertEqual(self.pending()[0].read_bytes(), original)
        self.assertEqual(capture.flush(self.config, ArchiveDouble()), 1)

    def test_production_archive_verifies_repository_visibility_and_account(self):
        archive = capture.GitHubArchive(self.config)
        for owner, private in [("AnotherUser", True), ("Crosby121", False)]:
            def request(method, path, **kwargs):
                return {"login": owner} if path == "/user" else {"full_name": capture.REPOSITORY, "private": private}
            with patch.object(archive, "request", request), self.assertRaises(ValueError):
                archive.verify()

    def test_secrets_are_redacted_before_local_or_github_persistence(self):
        secret = "github_pat_" + "X" * 60
        self.transcript.write_text('{"password":"do-not-save-password","text":"' + secret + '"}\n')
        event = self.event()
        event.update(authorization="Bearer private-value", prompt=self.config["github_token"])
        capture.capture(self.config, event, "copilot")
        archive = ArchiveDouble()
        capture.flush(self.config, archive)
        text = b"\n".join(archive.files.values()).decode()
        for secret_value in [secret, "do-not-save-password", "Bearer private-value", self.config["github_token"]]:
            self.assertNotIn(secret_value, text)
        self.assertIn("[REDACTED]", text)

    def test_unauthorized_transcript_is_not_read_and_an_error_is_recorded(self):
        private = self.root / "unauthorized.jsonl"
        private.write_text("Do not access this unrelated file")
        event = self.event()
        event["transcript_path"] = str(private)
        capture.capture(self.config, event, "codex")
        record = json.loads(self.pending()[0].read_text())
        self.assertFalse(record["transcript_objects"])
        self.assertIn("outside", record["capture_error"])
        self.assertNotIn(private.read_text(), json.dumps(record))

    def test_worker_follows_final_transcript_writes_after_the_ui_is_gone(self):
        capture.capture(self.config, self.event(), "codex")
        self.transcript.write_text(self.transcript.read_text() + '{"role":"assistant","text":"Final saved response"}\n')
        capture.monitor_transcripts(self.config)
        self.assertEqual(len(self.pending()), 2)
        archive = ArchiveDouble()
        capture.flush(self.config, archive)
        self.assertIn(self.transcript.read_bytes(), archive.files.values())

    def test_browser_capture_requires_tracking_and_reports_visible_only_coverage(self):
        event = {"url": "https://chatgpt.com/c/example", "event": "browser_checkpoint", "messages": [{"role": "user", "text": "Website task"}]}
        with self.assertRaises(ValueError):
            capture.capture(self.config, event, "browser")
        event["tracking_enabled"] = True
        capture.capture(self.config, event, "browser")
        self.assertIn("visible_rendered_messages_only", json.loads(self.pending()[0].read_text())["coverage"])
        event["url"] = "https://unrelated.example/chat"
        with self.assertRaises(ValueError):
            capture.capture(self.config, event, "browser")

    def test_stop_requests_one_handoff_retry_and_never_invents_completion(self):
        receipt = {"repository": "Crosby121/MirroriedLED-Public", "authenticated_client_id": "copilot", "commit": "1" * 40,
                   "session": {"id": "mcp-copilot-example", "status": "active"}}
        event = self.event("PostToolUse")
        event.update(tool_name="mcp__mirroriedLedWorkflow__start_session", tool_result={"text_result_for_llm": json.dumps(receipt)})
        capture.capture(self.config, event, "copilot")
        self.assertEqual(capture.stop_output(self.config, self.event())["decision"], "block")
        self.assertNotIn("decision", capture.stop_output(self.config, {**self.event(), "stop_hook_active": True}))
        receipt["session"]["status"] = "completed"
        event.update(tool_name="mcp__mirroriedLedWorkflow__finish_session", tool_result={"text_result_for_llm": json.dumps(receipt)})
        capture.capture(self.config, event, "copilot")
        self.assertEqual(capture.stop_output(self.config, self.event()), {})

    def test_native_message_utf8_framing_saves_before_acknowledgment(self):
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.config))
        event = {"url": "https://chatgpt.com/c/example", "tracking_enabled": True, "event": "tab_closed", "messages": [{"role": "assistant", "text": "Saved ✓"}]}
        body = json.dumps(event, ensure_ascii=False).encode()
        result = subprocess.run([sys.executable, str(ROOT / "tools/ai_capture.py"), "native", "--config", str(config_path),
                                 "chrome-extension://" + capture.EXTENSION_ID + "/"],
                                input=struct.pack("<I", len(body)) + body, capture_output=True, check=True)
        length = struct.unpack("<I", result.stdout[:4])[0]
        self.assertEqual(length, len(result.stdout[4:]))
        response = json.loads(result.stdout[4:])
        self.assertTrue(response["saved_locally"])
        self.assertFalse(response["github_uploaded"])
        self.assertEqual(len(self.pending()), 1)


if __name__ == "__main__":
    unittest.main()
