#!/usr/bin/env python3
"""
Fintech Log Ingester — Splunk HEC
Sends sample logs to Splunk HTTP Event Collector

Usage:
  pip install requests
  python ingest_to_splunk.py --hec-url https://your-splunk:8088 --token YOUR_HEC_TOKEN

For demo: runs continuously, replaying log file with current timestamps
"""

import argparse
import json
import re
import time
import requests
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
LOG_FILES = [
    "../logs/sample/payment-api.log",
    "../logs/sample/ui-app.log",
]
INDEX     = "ocp_fintech"
SOURCETYPE = "ocp_fintech_logs"
REPLAY_INTERVAL = 2  # seconds between log lines (slow for demo effect)

# ── HEC send ────────────────────────────────────────────────────────────────
def send_event(hec_url: str, token: str, raw_line: str, verify_ssl: bool = False):
    url = f"{hec_url}/services/collector/raw"
    headers = {
        "Authorization": f"Splunk {token}",
        "Content-Type": "text/plain",
        "X-Splunk-Request-Channel": "fintech-observability-demo",
    }
    params = {"index": INDEX, "sourcetype": SOURCETYPE}
    # Replace timestamp with now for live demo feel
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    line = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z", now_ts, raw_line.strip())
    resp = requests.post(url, headers=headers, params=params, data=line, verify=verify_ssl, timeout=5)
    return resp.status_code, line

# ── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fintech log ingester for Splunk HEC")
    parser.add_argument("--hec-url",  required=True, help="Splunk HEC base URL e.g. https://splunk-host:8088")
    parser.add_argument("--token",    required=True, help="HEC token")
    parser.add_argument("--no-ssl",   action="store_true", help="Skip SSL verification")
    parser.add_argument("--once",     action="store_true", help="Send each file once (don't loop)")
    args = parser.parse_args()

    lines = []
    for f in LOG_FILES:
        p = Path(__file__).parent / f
        if p.exists():
            lines.extend(p.read_text().splitlines())
        else:
            print(f"[WARN] Log file not found: {p}", file=sys.stderr)

    if not lines:
        print("[ERROR] No log lines found. Check LOG_FILES paths.", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Loaded {len(lines)} log lines. Sending to {args.hec_url} → index={INDEX}")
    loop = True
    while loop:
        for line in lines:
            if not line.strip():
                continue
            status, sent = send_event(args.hec_url, args.token, line, verify_ssl=not args.no_ssl)
            icon = "✅" if status == 200 else "❌"
            print(f"{icon} [{status}] {sent[:100]}...")
            time.sleep(REPLAY_INTERVAL)
        if args.once:
            loop = False
        else:
            print("[INFO] Replay complete. Restarting loop for demo...")
            time.sleep(5)

if __name__ == "__main__":
    main()
