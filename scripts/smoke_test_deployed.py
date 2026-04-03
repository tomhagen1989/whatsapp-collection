#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


class SmokeTestError(RuntimeError):
    pass


def request_json(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SmokeTestError(f"Request failed for {url}: {exc}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SmokeTestError(f"Expected JSON from {url}, got: {body[:400]}") from exc
    return status, parsed


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeTestError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the deployed Receivables Copilot API")
    parser.add_argument("--base-url", required=True, help="Deployed base URL, for example https://app.up.railway.app")
    parser.add_argument("--business-name", default="GitHub Smoke Test Business")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    status, payload = request_json("GET", f"{base_url}/healthz")
    expect(status == 200, f"/healthz returned {status}")
    expect(payload.get("status") == "ok", f"Unexpected /healthz payload: {payload}")
    print("PASS /healthz")

    extraction_cases = [
        ("show Gupta", "customer_timeline"),
        ("Mehta paid 20000", "update_case"),
        ("1 promised Friday", "update_case"),
        ("who promised this week?", "promises_due"),
    ]
    for text, expected_intent in extraction_cases:
        status, payload = request_json("POST", f"{base_url}/ai/extract", {"text": text})
        expect(status == 200, f"/ai/extract returned {status} for {text!r}")
        expect(payload.get("intent") == expected_intent, f"Unexpected intent for {text!r}: {payload}")
        print(f"PASS /ai/extract -> {text!r}")

    status, payload = request_json(
        "POST",
        f"{base_url}/tenants",
        {"business_name": args.business_name, "timezone": args.timezone},
    )
    expect(status == 200, f"/tenants returned {status}")
    business_id = payload.get("business_id") or payload.get("tenant_id")
    expect(isinstance(business_id, int), f"Unexpected /tenants payload: {payload}")
    print(f"PASS /tenants -> business_id={business_id}")

    summary_url = f"{base_url}/summary/today?{urllib.parse.urlencode({'tenant_id': business_id})}"
    status, payload = request_json("GET", summary_url)
    expect(status == 200, f"/summary/today returned {status}")
    expect("verified" in payload, f"Unexpected /summary/today payload: {payload}")
    print("PASS /summary/today")

    webhook_cases = [
        ("top overdue", {"ok", "unknown"}),
        ("show Gupta", {"ok", "clarification_required"}),
        ("Mehta paid 20000", {"updated", "clarification_required", "confirmation_required"}),
    ]
    for text, allowed_statuses in webhook_cases:
        status, payload = request_json(
            "POST",
            f"{base_url}/webhooks/whatsapp",
            {"tenant_id": business_id, "text": text, "raw_payload": {}},
        )
        expect(status == 200, f"/webhooks/whatsapp returned {status} for {text!r}")
        expect(payload.get("status") in allowed_statuses, f"Unexpected webhook payload for {text!r}: {payload}")
        print(f"PASS /webhooks/whatsapp -> {text!r}")

    print("All smoke tests passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeTestError as exc:
        print(f"SMOKE TEST FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
