"""Capture retention, privacy, close recovery, immutable uploads and native framing."""

import importlib.util
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError


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

    def test_opaque_credentials_in_hook_and_json_transcript_keys_are_redacted(self):
        values = {key: 'opaque-' + key + '-with-"quote' for key in ['token', 'github_token', 'workflow_token', 'private_key', 'passwd', 'refreshToken', 'client_secret', 'STRIPE_SECRET_KEY', 'HOSTINGER_SSH_PRIVATE_KEY']}
        first = json.dumps({"settings": values, "tool_result": json.dumps({"token": "embedded-opaque-value"})})
        second = json.dumps({"text": 'Example {"passwd":"inline-opaque-value"}', "password": 123456789})
        self.transcript.write_text(first + '\n' + second + '\n')
        capture.capture(self.config, {**self.event(), **values}, "copilot")
        archive = ArchiveDouble()
        capture.flush(self.config, archive)
        text = b'\n'.join(archive.files.values()).decode()
        self.assertNotIn('opaque-', text)
        for value in [*values.values(), 'embedded-opaque-value', 'inline-opaque-value', '123456789']:
            self.assertNotIn(value, text)
        self.assertIn('[REDACTED]', text)
        self.assertNotIn('unfinished-opaque-value', capture.redact('{"token":"unfinished-opaque-value'))

    def test_plaintext_private_keys_are_redacted_before_archive_persistence(self):
        self.transcript = self.transcripts / 'chat.txt'
        self.transcript.write_text('Safe before\n-----BEGIN PRIVATE KEY-----\n'
                                   'synthetic-key-body-first\n123456789\n'
                                   '-----END PRIVATE KEY-----\nSafe after\n')
        capture.capture(self.config, self.event(), 'copilot')
        objects = list((Path(self.config['spool']) / 'objects').glob('*.txt'))
        self.assertTrue(objects)
        local = b'\n'.join(path.read_bytes() for path in objects).decode()
        self.assertNotIn('synthetic-key-body-first', local)
        self.assertNotIn('123456789', local)
        archive = ArchiveDouble()
        capture.flush(self.config, archive)
        saved = b'\n'.join(archive.files.values()).decode()
        self.assertNotIn('synthetic-key-body-first', saved)
        self.assertNotIn('123456789', saved)
        self.assertIn('Safe before', saved)
        self.assertIn('Safe after', saved)

    def test_unfinished_plaintext_private_key_masks_the_rest_of_the_block(self):
        self.transcript = self.transcripts / 'chat.txt'
        self.transcript.write_text('Safe before\n-----BEGIN OPENSSH PRIVATE KEY-----\n'
                                   'synthetic-unfinished-key-body\nmore-key-body')
        capture.capture(self.config, self.event(), 'codex')
        saved = b'\n'.join(path.read_bytes() for path in
                          (Path(self.config['spool']) / 'objects').glob('*.txt')).decode()
        self.assertNotIn('synthetic-unfinished-key-body', saved)
        self.assertNotIn('more-key-body', saved)
        self.assertIn('Safe before', saved)

    def test_jsonl_private_key_redaction_preserves_adjacent_records(self):
        first = json.dumps({'text': '-----BEGIN PRIVATE KEY-----\nsynthetic-jsonl-key-body'})
        second = json.dumps({'text': 'Safe adjacent JSONL record', 'token': 'synthetic-adjacent-token'})
        cleaned = capture.redact_transcript(first + '\n' + second + '\n', ())
        records = [json.loads(line) for line in cleaned.splitlines()]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]['text'], 'Safe adjacent JSONL record')
        self.assertEqual(records[1]['token'], '[REDACTED]')
        self.assertNotIn('synthetic-jsonl-key-body', cleaned)

    def test_local_upload_budget_defers_without_losing_the_queued_record(self):
        capture.capture(self.config, self.event(), "codex")
        archive = capture.GitHubArchive(self.config)
        contents = {}
        def request(method, path, body=None, missing_ok=False):
            if path == '/user': return {'login': 'Crosby121'}
            if path == '/repos/' + capture.REPOSITORY: return {'full_name': capture.REPOSITORY, 'private': True}
            if method == 'GET': return contents.get(path)
            data = base64.b64decode(body['content'])
            contents[path] = {'sha': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(), 'html_url': 'https://github.com/example'}
            return {'content': contents[path]}
        with patch.object(capture.time, 'time', return_value=10000), patch.object(archive, 'request', request):
            for writes in [30, 360]:
                capture.atomic(archive.budget_path, capture.encoded({'writes': [10000] * writes, 'retry_after': 0, 'failures': 0}))
                with self.assertRaises(capture.UploadDeferred): capture.flush(self.config, archive)
                self.assertEqual(len(self.pending()), 1)
                self.assertFalse(contents)
        with patch.object(capture.time, 'time', return_value=13601), patch.object(archive, 'request', request):
            self.assertEqual(capture.flush(self.config, archive), 1)
        self.assertFalse(self.pending())

    def test_github_retry_after_blocks_requests_until_the_advertised_time(self):
        archive = capture.GitHubArchive(self.config)
        failure = HTTPError('https://api.github.com/user', 429, 'Rate limited', {'Retry-After': '120'}, None)
        with patch.object(capture.time, 'time', return_value=10000), patch.object(archive.opener, 'open', side_effect=failure) as opened:
            with self.assertRaises(capture.UploadDeferred): archive.request('GET', '/user')
            with self.assertRaises(capture.UploadDeferred): archive.request('GET', '/user')
            self.assertEqual(opened.call_count, 1)
        self.assertEqual(archive.budget()['retry_after'], 10120)

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

    def test_worker_recovers_a_final_write_during_the_previous_checkpoint_read(self):
        original = Path.read_text
        appended = False
        def read_then_append(path, *args, **kwargs):
            nonlocal appended
            text = original(path, *args, **kwargs)
            if path == self.transcript and not appended:
                appended = True
                path.write_text(text + '{"role":"assistant","text":"Final text written during capture"}\n')
            return text
        with patch.object(Path, "read_text", read_then_append):
            capture.capture(self.config, self.event(), "codex")
        capture.monitor_transcripts(self.config)
        self.assertEqual(len(self.pending()), 2)
        self.assertEqual({json.loads(path.read_text())["platform_session_id"] for path in self.pending()}, {"native-session-1"})
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

    def test_masked_browser_text_retains_utf16_offsets_for_later_deltas(self):
        raw = 'Prefix 🙂 {"token":"hidden-opaque-credential"} old tail'
        event = {"url": "https://chatgpt.com/c/example", "tracking_enabled": True, "event": "browser_checkpoint",
                 "messages": [{"role": "assistant", "text": raw}]}
        capture.capture(self.config, event, "browser")
        base = json.loads(self.pending()[0].read_text())["payload"]["messages"][0]["text"]
        self.assertNotIn('hidden-opaque-credential', base)
        self.assertEqual(len(base.encode('utf-16-le')), len(raw.encode('utf-16-le')))
        prefix = raw[:-len('old tail')]
        offset = len(prefix.encode('utf-16-le')) // 2
        suffix = 'new tail'
        event['messages'] = [{"role": "assistant", "text": suffix, "offset": offset, "replace_from": offset}]
        record_id = capture.capture(self.config, event, "browser")
        delta = json.loads((Path(self.config['spool']) / 'outbox' / (record_id + '.json')).read_text())['payload']['messages'][0]
        result = (base.encode('utf-16-le')[:delta['replace_from'] * 2] + delta['text'].encode('utf-16-le')).decode('utf-16-le')
        self.assertTrue(result.endswith('new tail'))
        self.assertNotIn('old tail', result)
        self.assertNotIn('hidden-opaque-credential', result)

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
