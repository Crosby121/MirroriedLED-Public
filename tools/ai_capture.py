#!/usr/bin/env python3
"""Durable private AI chat capture, native messaging, and GitHub retry worker."""

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "mirroriedled-private/ai-capture/config.json"
REPOSITORY = "Crosby121/MirroriedLED-AI-History"
SOURCES = {"copilot": "GitHub Copilot", "codex": "ChatGPT / local Codex", "browser": "Tracked browser AI chat"}
EXTENSION_ID = "hdecleonacegadhfjjnlioafnamnljkg"
SECRET = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)|(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{30,}|mlwf_[A-Za-z0-9_-]{40,}", re.DOTALL)
SENSITIVE_NAMES = r"(?:password|passwd|token|bearer|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|cookie|private[_-]?key|secret|client[_-]?secret|github[_-]?token|workflow[_-]?token)"
SENSITIVE_KEY = re.compile(r"^" + SENSITIVE_NAMES + r"$", re.I)
INLINE_SECRET = re.compile(r'("' + SENSITIVE_NAMES + r'"\s*:\s*)"(?:\\.|[^"\\])*(?:"|\\?\Z)', re.I)


def require(condition, message):
    if not condition:
        raise ValueError(message)


class UploadDeferred(ValueError):
    """A durable queue must wait for its local budget or GitHub's retry time."""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def redact(value, known_secrets=()):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SENSITIVE_KEY.fullmatch(str(key)) else redact(item, known_secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, known_secrets) for item in value]
    if isinstance(value, str):
        for secret in known_secrets:
            if secret and len(secret) >= 12:
                value = value.replace(secret, "[REDACTED]")
        return INLINE_SECRET.sub(r'\1"[REDACTED]"', SECRET.sub("[REDACTED]", value))
    return value


def redact_transcript(text, known_secrets):
    # Decode native JSON/JSONL before filtering so escaped message/tool JSON is
    # treated like structured hook payloads. Preserve unchanged text exactly.
    def filtered(part):
        try:
            original = json.loads(part)
        except (ValueError, TypeError):
            return redact(part, known_secrets)
        cleaned = redact(original, known_secrets)
        if cleaned == original:
            return part
        return json.dumps(cleaned, ensure_ascii=True, separators=(",", ":")) + ("\n" if part.endswith("\n") else "")
    try:
        json.loads(text)
    except ValueError:
        return "".join(filtered(line) for line in text.splitlines(keepends=True))
    return filtered(text)


def safe(path):
    path = Path(path).absolute()
    require(not any(parent.is_symlink() for parent in (path, *path.parents)), "Capture paths must not use symlinks")
    return path


def atomic(path, data):
    path = safe(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".capture-", dir=path.parent)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        else:
            os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_config(path):
    path = safe(path)
    config = json.loads(path.read_text())
    require(config.get("repository") == REPOSITORY, "Use the dedicated private Mirroried LED AI history repository")
    require(isinstance(config.get("github_token"), str) and len(config["github_token"]) >= 30, "Configure the private history GitHub token")
    require(isinstance(config.get("transcript_roots"), list), "Configure authorized native transcript directories")
    config["workspace"] = str(safe(config["workspace"]))
    config["spool"] = str(safe(config["spool"]))
    require(Path(config["spool"]).name == "spool", "Use a private spool directory")
    return config


def capture(config, event, source):
    require(source in SOURCES and isinstance(event, dict), "Unknown capture source or event")
    workspace = safe(config["workspace"])
    if source != "browser":
        cwd = safe(event.get("cwd", workspace))
        require(cwd == workspace or workspace in cwd.parents, "This hook event belongs to another workspace")
    else:
        url = event.get("url", "")
        require(re.match(r"^https://(?:chatgpt\.com|agent\.hostinger\.com)/", url), "Browser capture is limited to the configured AI sites")
        require(event.get("tracking_enabled") is True, "Browser chat must be explicitly tracked")
    spool = safe(config["spool"])
    secrets = [config["github_token"], config.get("workflow_token", "")]
    cleaned = redact(event, secrets)
    transcript = event.get("transcript_path") or event.get("transcriptPath")
    objects = []
    coverage = "available_hook_payload"
    error = None
    if isinstance(transcript, str) and transcript:
        try:
            path = safe(transcript)
            roots = [safe(root) for root in config["transcript_roots"]]
            require(any(root == path.parent or root in path.parents for root in roots), "Transcript path is outside the authorized directories")
            require(path.suffix.lower() in {".json", ".jsonl", ".ndjson", ".txt"} and path.is_file(), "Unsupported transcript file")
            observed = path.stat()
            require(observed.st_size <= 20971520, "Transcript exceeds the 20 MiB capture limit; export it in parts")
            raw_text = path.read_text(encoding="utf-8")
            require(len(raw_text.encode()) <= 20971520, "Transcript exceeds the 20 MiB capture limit; export it in parts")
            text = redact_transcript(raw_text, secrets)
            for offset in range(0, len(text), 131072):
                content = text[offset:offset + 131072].encode()
                object_id = digest(content)
                atomic(spool / "objects" / (object_id + ".txt"), content)
                objects.append(object_id)
            coverage = "available_native_transcript; attachments and unavailable internal context are not exported"
            # A PC worker follows registered files even after the UI disappears.
            monitor_id = digest(str(path).encode())
            atomic(spool / "monitors" / (monitor_id + ".json"), encoded({"path": str(path), "source": source,
                   "cwd": str(workspace), "session_id": str(event.get("session_id") or event.get("sessionId") or "unknown"),
                   "signature": [observed.st_mtime_ns, observed.st_size]}))
        except (ValueError, OSError, UnicodeError) as failure:
            error = str(failure)
            coverage = "hook_payload_only; transcript_capture_failed"
    if source == "browser":
        coverage = "visible_rendered_messages_only; virtualized, unloaded, hidden messages and attachments may be absent"
    record = {"schema_version": 1, "captured_at": event.get("captured_at") or now(), "source": source,
              "application": SOURCES[source], "application_identity": "configured_capture_source",
              "platform_session_id": str(event.get("session_id") or event.get("sessionId") or event.get("url") or "unknown"),
              "event": str(event.get("hook_event_name") or event.get("event") or "checkpoint"),
              "coverage": coverage, "payload": cleaned, "transcript_objects": objects,
              "capture_error": error, "redaction": "Known credentials and recognizable secret formats removed; best-effort filter"}
    record_id = digest(encoded(record))
    atomic(spool / "outbox" / (record_id + ".json"), encoded(record))
    remember_handoff(config, event, source)
    return record_id


def workflow_receipt(value, depth=0):
    if depth > 8:
        return None
    if isinstance(value, str):
        try:
            return workflow_receipt(json.loads(value), depth + 1)
        except (ValueError, TypeError):
            return None
    if isinstance(value, dict):
        if value.get("repository") == "Crosby121/MirroriedLED-Public" and isinstance(value.get("session"), dict):
            return value
        for child in value.values():
            found = workflow_receipt(child, depth + 1)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = workflow_receipt(child, depth + 1)
            if found:
                return found
    return None


def remember_handoff(config, event, source):
    name = event.get("tool_name") or event.get("toolName") or ""
    if not re.search(r"(?:start_session|finish_session)$", str(name)):
        return
    receipt = workflow_receipt(event.get("tool_response") or event.get("tool_result") or event.get("toolResult"))
    if not receipt or not (receipt.get("commit") or receipt.get("replayed")):
        return
    expected = {"copilot": "copilot", "codex": "chatgpt-codex"}.get(source)
    if receipt.get("authenticated_client_id") != expected:
        return
    session = receipt["session"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", str(session.get("id", ""))):
        return
    platform_id = str(event.get("session_id") or event.get("sessionId") or "unknown")
    atomic(Path(config["spool"]) / "handoffs" / (digest(platform_id.encode()) + ".json"),
           encoded({"workflow_session_id": session["id"], "status": session.get("status"), "evidence_url": receipt.get("evidence_url")}))


def stop_output(config, event):
    platform_id = str(event.get("session_id") or event.get("sessionId") or "unknown")
    path = Path(config["spool"]) / "handoffs" / (digest(platform_id.encode()) + ".json")
    if path.exists() and json.loads(path.read_text()).get("status") == "active":
        if event.get("stop_hook_active") is not True:
            return {"decision": "block", "reason": "Before finishing this turn, use finish_session to publish the verified completed or blocked task handoff in GitHub. The available chat checkpoint is saved locally; do not claim full synchronization without an upload receipt."}
        return {"systemMessage": "GitHub task completion is still unconfirmed. The capture checkpoint remains in the private retry queue."}
    return {}


def monitor_transcripts(config):
    spool = Path(config["spool"])
    for marker in (spool / "monitors").glob("*.json"):
        monitor = json.loads(safe(marker).read_text())
        path = safe(monitor["path"])
        if path.is_file() and [path.stat().st_mtime_ns, path.stat().st_size] != monitor["signature"]:
            capture(config, {"hook_event_name": "file_checkpoint", "cwd": monitor["cwd"],
                            "transcript_path": str(path), "session_id": monitor.get("session_id", "file-" + marker.stem)}, monitor["source"])


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


class GitHubArchive:
    def __init__(self, config):
        self.token = config["github_token"]
        self.repo = config["repository"]
        require(self.repo == REPOSITORY, "Unexpected archive destination")
        self.budget_path = safe(Path(config["spool"]) / "upload-budget.json")
        self.opener = build_opener(NoRedirects())

    def budget(self):
        state = json.loads(self.budget_path.read_text()) if self.budget_path.exists() else {"writes": [], "retry_after": 0, "failures": 0}
        require(isinstance(state.get("writes"), list) and len(state["writes"]) <= 360
                and all(isinstance(value, (int, float)) for value in state["writes"])
                and isinstance(state.get("retry_after"), (int, float)) and isinstance(state.get("failures"), int), "Invalid private upload budget")
        return state

    def check_backoff(self):
        if self.budget()["retry_after"] > time.time():
            raise UploadDeferred("GitHub retry time has not arrived; checkpoints remain queued")

    def reserve_write(self):
        state, clock = self.budget(), time.time()
        state["writes"] = [value for value in state["writes"] if value > clock - 3600]
        if len(state["writes"]) >= 360 or sum(value > clock - 60 for value in state["writes"]) >= 30:
            raise UploadDeferred("Private upload budget reached; checkpoints remain queued")
        state["writes"].append(clock)  # Reserve before sending, including an uncertain response.
        atomic(self.budget_path, encoded(state))

    def defer(self, headers):
        headers = headers or {}
        state, clock = self.budget(), time.time()
        delay = min(3600, 60 * (2 ** min(max(state["failures"], 0), 6)))
        retry = str(headers.get("Retry-After", ""))
        if retry.isdigit():
            delay = max(delay, int(retry))
        elif retry:
            try:
                delay = max(delay, parsedate_to_datetime(retry).timestamp() - clock)
            except (ValueError, TypeError, OverflowError):
                pass
        reset = str(headers.get("X-RateLimit-Reset", ""))
        if headers.get("X-RateLimit-Remaining") == "0" and reset.isdigit():
            delay = max(delay, int(reset) - clock)
        state.update(retry_after=clock + delay, failures=state["failures"] + 1)
        atomic(self.budget_path, encoded(state))

    def succeeded(self):
        state = self.budget()
        if state["failures"]:
            state.update(failures=0, retry_after=0)
            atomic(self.budget_path, encoded(state))

    def request(self, method, path, body=None, missing_ok=False):
        self.check_backoff()
        data = encoded(body) if body is not None else None
        headers = {"Accept": "application/vnd.github+json", "Authorization": "Bearer " + self.token,
                   "User-Agent": "MirroriedLED-AICapture/1.0", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"}
        try:
            response = self.opener.open(Request("https://api.github.com" + path, data=data, headers=headers, method=method), timeout=30)
        except HTTPError as failure:
            if missing_ok and failure.code == 404:
                return None
            if failure.code in {403, 429}:
                self.defer(failure.headers)
                raise UploadDeferred("GitHub requested a retry delay; checkpoints remain queued") from None
            # Never echo raw error bodies, headers, or credentials.
            raise ValueError("GitHub archive access failed (HTTP %d)" % failure.code) from None
        with response:
            return json.loads(response.read())

    def verify(self):
        account = self.request("GET", "/user")
        repo = self.request("GET", "/repos/" + self.repo)
        require(account.get("login") == "Crosby121", "Archive token belongs to another GitHub account")
        require(repo.get("private") is True and repo.get("full_name") == self.repo,
                "Full chat archives require the dedicated PRIVATE GitHub repository; upload refused")

    def put(self, path, data):
        require(re.fullmatch(r"(?:objects/[a-f0-9]{64}\.txt|archive/(?:copilot|codex|browser)/[a-f0-9]{32}/events/[a-f0-9]{64}\.json)", path), "Unsafe archive path")
        endpoint = "/repos/" + self.repo + "/contents/" + path
        blob_sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        existing = self.request("GET", endpoint, missing_ok=True)
        if existing is not None:
            require(existing.get("sha") == blob_sha, "An immutable archive record has different contents")
            return existing.get("html_url")
        self.reserve_write()
        try:
            created = self.request("PUT", endpoint, {"message": "Save Mirroried LED AI checkpoint", "content": base64.b64encode(data).decode()})
        except UploadDeferred:
            raise
        except ValueError:
            # A lost response or concurrent upload may have already created the exact blob.
            existing = self.request("GET", endpoint, missing_ok=True)
            require(existing is not None and existing.get("sha") == blob_sha, "Archive upload is unconfirmed; retained in the local retry queue")
            return existing.get("html_url")
        self.succeeded()
        return created["content"]["html_url"]


@contextmanager
def worker_lock(spool):
    spool = safe(spool)
    spool.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(safe(spool / "worker.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        # OS locks release automatically when a killed worker closes its descriptor.
        os.close(descriptor)


def flush(config, archive=None):
    spool = safe(config["spool"])
    uploaded = 0
    with worker_lock(spool):
        pending = sorted((spool / "outbox").glob("*.json"))
        if not pending:
            return 0
        archive = archive or GitHubArchive(config)
        archive.verify()  # Check privacy on EVERY batch, including after visibility changes.
        for path in pending:
            data = safe(path).read_bytes()
            require(digest(data) == path.stem, "A queued checkpoint failed its integrity check")
            record = json.loads(data)
            require(record["source"] in SOURCES, "Unknown checkpoint source")
            for object_id in record["transcript_objects"]:
                require(re.fullmatch(r"[a-f0-9]{64}", object_id), "Invalid transcript object ID")
                content = safe(spool / "objects" / (object_id + ".txt")).read_bytes()
                require(digest(content) == object_id, "Transcript checkpoint integrity check failed")
                # Local receipts avoid re-uploading unchanged chunks across checkpoints.
                marker = spool / "object-receipts" / (object_id + ".json")
                if not marker.exists():
                    url = archive.put("objects/" + object_id + ".txt", content)
                    atomic(marker, encoded({"repository": config["repository"], "url": url}))
            session = digest(record["platform_session_id"].encode())[:32]
            remote_path = "archive/%s/%s/events/%s.json" % (record["source"], session, path.stem)
            url = archive.put(remote_path, data)
            atomic(spool / "uploaded" / path.name, encoded({"record_id": path.stem, "uploaded_at": now(), "repository": config["repository"], "url": url}))
            path.unlink()
            uploaded += 1
    return uploaded


def native(config):
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    while True:
        header = sys.stdin.buffer.read(4)
        if not header:
            return 0
        require(len(header) == 4, "Invalid native message header")
        length = struct.unpack("<I", header)[0]
        require(0 < length <= 1048576, "Native message is too large")
        body = sys.stdin.buffer.read(length)
        require(len(body) == length, "Incomplete native message")
        try:
            event = json.loads(body)
            if event.get("command") == "status":
                spool = Path(config["spool"])
                response = {"pending": len(list((spool / "outbox").glob("*.json"))),
                            "uploaded": len(list((spool / "uploaded").glob("*.json")))}
            else:
                record_id = capture(config, event, "browser")
                response = {"saved_locally": True, "record_id": record_id, "github_uploaded": False}
        except Exception:
            response = {"saved_locally": False, "error": "Capture failed; the browser will retain its retry copy."}
        output = encoded(response)
        sys.stdout.buffer.write(struct.pack("<I", len(output)) + output)
        sys.stdout.buffer.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("hook", "flush", "watch", "native", "status"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--source", choices=tuple(SOURCES), default="copilot")
    parser.add_argument("--event", default="checkpoint")
    args, _native_origin = parser.parse_known_args()
    try:
        config = load_config(args.config)
        if args.command == "native":
            require("chrome-extension://" + EXTENSION_ID + "/" in _native_origin, "Unknown browser extension origin")
            return native(config)
        if args.command == "hook":
            event = json.loads(sys.stdin.read(2097152))
            event.setdefault("hook_event_name", args.event)
            capture(config, event, args.source)
            print(json.dumps(stop_output(config, event) if args.event == "Stop" else {}))
        elif args.command == "flush":
            print("ARCHIVED_CHECKPOINTS=%d" % flush(config))
        elif args.command == "status":
            spool = Path(config["spool"])
            print("PENDING_CHECKPOINTS=%d" % len(list((spool / "outbox").glob("*.json"))))
            print("UPLOADED_RECEIPTS=%d" % len(list((spool / "uploaded").glob("*.json"))))
        else:
            while True:
                try:
                    monitor_transcripts(config)
                    flush(config)
                    atomic(Path(config["spool"]) / "worker-status.json", encoded({"checked_at": now(), "result": "ok"}))
                except UploadDeferred:
                    atomic(Path(config["spool"]) / "worker-status.json", encoded({"checked_at": now(), "result": "rate_wait"}))
                except Exception:
                    atomic(Path(config["spool"]) / "worker-status.json", encoded({"checked_at": now(), "result": "retry_pending"}))
                time.sleep(30)
    except UploadDeferred:
        print("GitHub upload deferred by its retry time or the local write budget; pending checkpoints are retained.", file=sys.stderr)
        return 1
    except Exception:
        # Local hook errors remain visible, but private payloads/credentials never enter stdout.
        if args.command == "hook":
            print('{"systemMessage":"AI archive capture is not configured or failed; check the local capture status."}')
        else:
            print("AI capture is not configured or could not complete; pending checkpoints are retained.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
