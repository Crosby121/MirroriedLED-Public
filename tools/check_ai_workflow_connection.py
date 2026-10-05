#!/usr/bin/env python3
"""Read-only deployment smoke check. Credentials are read from private files."""

import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def check(url, token=None):
    if url != "https://mirroriedled.com/ai-workflow/mcp.php":
        raise ValueError("Use the configured HTTPS Mirroried LED endpoint")
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = {"jsonrpc": "2.0", "id": "deployment-check", "method": "tools/call", "params": {"name": "read_state", "arguments": {}}}
    opener = build_opener(NoRedirects())
    try:
        response = opener.open(Request(url, data=json.dumps(payload).encode(), headers=headers), timeout=120)
    except HTTPError as error:
        response = error
    with response:
        if not token:
            if response.status != 401:
                raise ValueError("Anonymous access must return 401")
            return
        if response.status != 200:
            raise ValueError("Authenticated connection failed")
        data = json.loads(response.read())
    result = data.get("result", {})
    content = result.get("structuredContent", {})
    if result.get("isError", True) or content.get("repository") != "Crosby121/MirroriedLED-Public" or content.get("service_github_account") != "Crosby121":
        raise ValueError("Connector GitHub read or service-account verification failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://mirroriedled.com/ai-workflow/mcp.php")
    parser.add_argument("--credentials")
    parser.add_argument("--client-id", default="copilot")
    args = parser.parse_args()
    try:
        token = json.loads(Path(args.credentials).read_text())[args.client_id] if args.credentials else None
        check(args.url, token)
    except Exception:
        print("Workflow connection check failed; inspect the endpoint, private configuration and credentials.", file=sys.stderr)
        return 1
    print("WORKFLOW_AUTHENTICATED_READ_PASSED" if token else "WORKFLOW_ANONYMOUS_ACCESS_DENIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
