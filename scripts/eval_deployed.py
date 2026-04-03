#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal


class EvalError(RuntimeError):
    pass


SEED_CSV = """Date,Ref No.,Party's Name,Opening Amount,Pending Amount,Due On,Overdue by days,Mobile,Sales Person,Remarks,Party Code
2026-01-12,INV-2401-118,Gupta Traders,\"48,500\",\"48,500\",2026-02-11,51,9876543210,Rohit Sharma,Follow up after Friday market,CUST-001
2026-01-28,INV-2401-207,Mehta Agencies,\"95,000\",\"95,000\",2026-02-27,35,9810012345,Anita Verma,Promised 20000 next week,CUST-002
2026-02-03,INV-2402-014,Shree Balaji Distributors,\"76,000\",\"76,000\",2026-03-05,29,9899001122,Rohit Sharma,Escalate with owner if no reply,CUST-003
2026-02-15,INV-2402-095,NK Pharma Retail,\"33,500\",\"33,500\",2026-03-16,18,9822044455,Priya Nair,Waiting for debit note approval,CUST-004
2026-02-20,INV-2402-143,Sai Medical Hall,\"15,800\",\"5,800\",2026-03-21,13,9933007788,Priya Nair,Partial payment received on call,CUST-005
2026-03-01,INV-2403-021,Kaveri Super Stores,\"42,000\",\"42,000\",2026-03-31,3,9888877766,Anita Verma,New overdue case,CUST-006
2026-03-02,INV-2403-044,Alpha Pharma,\"60,000\",\"60,000\",2026-03-24,22,9777700011,Rohit Sharma,Largest Alpha invoice,CUST-007
2026-03-08,INV-2403-088,Alpha Pharma,\"20,000\",\"20,000\",2026-04-05,10,9777700011,Rohit Sharma,Second Alpha invoice,CUST-007
"""

EXPECTED_TOTAL = Decimal("380800.00")
EXPECTED_BUCKET_0_30 = Decimal("237300.00")
EXPECTED_BUCKET_31_60 = Decimal("143500.00")
EXPECTED_TOTAL_AFTER_MEHTA_PAYMENT = Decimal("360800.00")
EXPECTED_BUCKET_31_60_AFTER_MEHTA_PAYMENT = Decimal("123500.00")
EXPECTED_ALPHA_TOTAL_AFTER_CONFIRM = Decimal("75000.00")


def normalize_base_url(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        raise EvalError("Base URL is required")
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise EvalError(f"Invalid base URL: {value!r}")
    return cleaned


def request_json(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise EvalError(f"Request failed for {url}: {exc}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise EvalError(f"Expected JSON from {url}, got: {body[:500]}") from exc
    return status, parsed


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise EvalError(message)


def expect_decimal(value: str | int | float, expected: Decimal, label: str) -> None:
    actual = Decimal(str(value))
    expect(actual == expected, f"Unexpected {label}: expected {expected}, got {actual}")


def extract_confirmation_token(reply_text: str) -> str:
    matches = re.findall(r"confirm\s+([0-9a-fA-F]{8})", reply_text, flags=re.IGNORECASE)
    if not matches:
        raise EvalError(f"Could not find confirmation token in reply: {reply_text}")
    return matches[-1]


def get_summary(base_url: str, business_id: int) -> dict:
    summary_url = f"{base_url}/summary/today?{urllib.parse.urlencode({'tenant_id': business_id})}"
    status, payload = request_json("GET", summary_url)
    expect(status == 200, f"/summary/today returned {status}")
    return payload


def get_timeline(base_url: str, business_id: int, customer_id: int) -> dict:
    url = f"{base_url}/customers/{customer_id}/timeline?{urllib.parse.urlencode({'tenant_id': business_id})}"
    status, payload = request_json("GET", url)
    expect(status == 200, f"/customers/{{id}}/timeline returned {status} for customer {customer_id}")
    return payload


def webhook(base_url: str, business_id: int, text: str) -> dict:
    status, payload = request_json(
        "POST",
        f"{base_url}/webhooks/whatsapp",
        {"tenant_id": business_id, "text": text, "raw_payload": {}},
    )
    expect(status == 200, f"/webhooks/whatsapp returned {status} for {text!r}")
    expect(payload.get("status") != "error", f"Webhook returned error for {text!r}: {payload}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the deployed Receivables Copilot app")
    parser.add_argument("--base-url", required=True, help="Deployed base URL, for example https://app.up.railway.app or app.up.railway.app")
    parser.add_argument("--business-name", default="GitHub Eval Business")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url)
    report: dict[str, object] = {"base_url": base_url, "checks": []}

    status, payload = request_json("GET", f"{base_url}/healthz")
    expect(status == 200 and payload.get("status") == "ok", f"Unexpected /healthz payload: {payload}")
    report["checks"].append("healthz")
    print("PASS /healthz")

    extraction_cases = [
        ("show Alpha Pharma", "customer_timeline"),
        ("Alpha Pharma paid 5000", "update_case"),
        ("1 promised tomorrow", "update_case"),
        ("what is going on", "unknown"),
    ]
    for text, expected_intent in extraction_cases:
        status, payload = request_json("POST", f"{base_url}/ai/extract", {"text": text})
        expect(status == 200, f"/ai/extract returned {status} for {text!r}")
        expect(payload.get("intent") == expected_intent, f"Unexpected intent for {text!r}: {payload}")
        report["checks"].append(f"ai_extract:{text}")
        print(f"PASS /ai/extract -> {text!r}")

    unique_business_name = f"{args.business_name} {int(time.time())}"
    status, payload = request_json(
        "POST",
        f"{base_url}/tenants",
        {"business_name": unique_business_name, "timezone": args.timezone},
    )
    expect(status == 200, f"/tenants returned {status}")
    business_id = payload.get("business_id") or payload.get("tenant_id")
    expect(isinstance(business_id, int), f"Unexpected /tenants payload: {payload}")
    report["business_id"] = business_id
    report["checks"].append("create_business")
    print(f"PASS /tenants -> business_id={business_id}")

    status, payload = request_json(
        "POST",
        f"{base_url}/imports/paste",
        {"tenant_id": business_id, "file_name": "github-eval.csv", "csv_text": SEED_CSV},
    )
    expect(status == 200, f"/imports/paste returned {status}")
    expect(payload.get("status") == "success", f"Unexpected /imports/paste payload: {payload}")
    expect(payload.get("rows") == 8, f"Expected 8 imported rows, got {payload}")
    report["checks"].append("paste_import")
    print("PASS /imports/paste")

    history_url = f"{base_url}/imports/history?{urllib.parse.urlencode({'tenant_id': business_id})}"
    status, payload = request_json("GET", history_url)
    expect(status == 200, f"/imports/history returned {status}")
    imports = payload.get("imports") or []
    expect(imports, f"Expected import history entries, got {payload}")
    latest_import = imports[0]
    expect(latest_import.get("status") == "success", f"Latest import did not succeed: {latest_import}")
    expect(latest_import.get("rows") == 8, f"Latest import rows mismatch: {latest_import}")
    expect(latest_import.get("snapshot_version") == 1, f"Latest snapshot version mismatch: {latest_import}")
    report["checks"].append("import_history")
    print("PASS /imports/history")

    summary = get_summary(base_url, business_id)
    expect(summary.get("verified") is True, f"Summary numbers were not verified: {summary}")
    brief = summary.get("brief") or {}
    expect_decimal(brief.get("total_outstanding"), EXPECTED_TOTAL, "initial total outstanding")
    expect_decimal(brief.get("ageing_buckets", {}).get("0-30"), EXPECTED_BUCKET_0_30, "initial 0-30 bucket")
    expect_decimal(brief.get("ageing_buckets", {}).get("31-60"), EXPECTED_BUCKET_31_60, "initial 31-60 bucket")
    expect(brief.get("snapshot_version") == 1, f"Initial summary snapshot mismatch: {brief}")
    attention_items = brief.get("attention_items") or []
    name_to_customer = {item["customer_name"]: item["customer_id"] for item in attention_items}
    expect("Mehta Agencies" in name_to_customer, f"Mehta Agencies missing from attention items: {attention_items}")
    expect("Alpha Pharma" in name_to_customer, f"Alpha Pharma missing from attention items: {attention_items}")
    mehta_customer_id = name_to_customer["Mehta Agencies"]
    alpha_customer_id = name_to_customer["Alpha Pharma"]
    top_customer_id = attention_items[0]["customer_id"]
    report["checks"].append("initial_summary")
    print("PASS /summary/today initial assertions")

    mehta_timeline = get_timeline(base_url, business_id, mehta_customer_id)
    expect_decimal(mehta_timeline.get("total_outstanding"), Decimal("95000.00"), "Mehta initial total")
    expect(mehta_timeline.get("active_case_count") == 1, f"Unexpected Mehta active case count: {mehta_timeline}")
    report["checks"].append("timeline_mehta_initial")
    print("PASS /customers/{id}/timeline -> Mehta initial")

    payload = webhook(base_url, business_id, "show Not A Real Customer")
    expect(payload.get("status") == "clarification_required", f"Expected clarification for missing customer: {payload}")
    report["checks"].append("webhook_missing_customer")
    print("PASS webhook missing-customer clarification")

    payload = webhook(base_url, business_id, "top overdue")
    expect(payload.get("status") == "ok", f"Expected top overdue success: {payload}")
    report["checks"].append("webhook_top_overdue")
    print("PASS webhook top overdue")

    payload = webhook(base_url, business_id, "show Alpha Pharma")
    expect(payload.get("status") == "ok", f"Expected Alpha timeline success: {payload}")
    report["checks"].append("webhook_show_alpha")
    print("PASS webhook show Alpha Pharma")

    payload = webhook(base_url, business_id, "1 promised tomorrow")
    expect(payload.get("status") == "confirmation_required", f"Expected confirmation for list reference update: {payload}")
    token = extract_confirmation_token(payload.get("reply_text", ""))
    payload = webhook(base_url, business_id, f"confirm {token}")
    expect(payload.get("status") == "updated", f"Expected confirmed update success: {payload}")
    top_timeline = get_timeline(base_url, business_id, top_customer_id)
    expect(any(case.get("status") == "promised" for case in top_timeline.get("cases", [])), f"Expected promised case after confirmation: {top_timeline}")
    report["checks"].append("webhook_list_reference_confirmation")
    print("PASS webhook list-reference confirmation flow")

    payload = webhook(base_url, business_id, "Mehta Agencies paid 20000")
    expect(payload.get("status") == "updated", f"Expected Mehta payment update success: {payload}")
    summary = get_summary(base_url, business_id)
    brief = summary.get("brief") or {}
    expect_decimal(brief.get("total_outstanding"), EXPECTED_TOTAL_AFTER_MEHTA_PAYMENT, "post-Mehta total outstanding")
    expect_decimal(brief.get("ageing_buckets", {}).get("31-60"), EXPECTED_BUCKET_31_60_AFTER_MEHTA_PAYMENT, "post-Mehta 31-60 bucket")
    mehta_timeline = get_timeline(base_url, business_id, mehta_customer_id)
    expect_decimal(mehta_timeline.get("total_outstanding"), Decimal("75000.00"), "Mehta post-payment total")
    report["checks"].append("webhook_exact_payment_update")
    print("PASS webhook exact payment update")

    payload = webhook(base_url, business_id, "Alpha Pharma paid 5000")
    expect(payload.get("status") == "confirmation_required", f"Expected confirmation for multi-invoice Alpha update: {payload}")
    token = extract_confirmation_token(payload.get("reply_text", ""))
    payload = webhook(base_url, business_id, f"confirm {token}")
    expect(payload.get("status") == "updated", f"Expected Alpha confirmed update success: {payload}")
    alpha_timeline = get_timeline(base_url, business_id, alpha_customer_id)
    expect_decimal(alpha_timeline.get("total_outstanding"), EXPECTED_ALPHA_TOTAL_AFTER_CONFIRM, "Alpha post-confirm total")
    amounts = sorted(Decimal(str(case.get("amount_outstanding"))) for case in alpha_timeline.get("cases", []))
    expect(amounts == [Decimal("20000.00"), Decimal("55000.00")], f"Unexpected Alpha case balances: {alpha_timeline}")
    report["checks"].append("webhook_multi_invoice_confirmation")
    print("PASS webhook multi-invoice confirmation flow")

    print("All deployed eval checks passed.")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvalError as exc:
        print(f"DEPLOYED EVAL FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
