#!/usr/bin/env python3
"""
Chaos Injection — Auth Service Latency Spike
Sends a burst of high-latency auth failure logs to Splunk HEC
to simulate a live incident during demo.

Usage:
  python chaos_inject.py --hec-url https://your-splunk:8088 --token YOUR_HEC_TOKEN
"""

import argparse
import random
import requests
import time
from datetime import datetime, timezone

INDEX      = "ocp_fintech"
SOURCETYPE = "ocp_fintech_logs"

CHAOS_TEMPLATES = [
    'app=auth-service pod=auth-service-5c6d7e-mn3qr namespace=fintech-prod method=POST endpoint=/api/v1/auth/verify status=500 user_id=U{uid} customer_tier={tier} amount={amount} currency=INR duration_ms={latency} region={region} workflow_step=auth_verify error=auth_timeout error_code=AUTH_SVC_TIMEOUT trace_id={tid} correlation_id=CHAOS-{cid}',
    'app=payment-api pod=payment-api-7d9f8b-xk2lp namespace=fintech-prod method=POST endpoint=/api/v1/transfer status=500 user_id=U{uid} customer_tier={tier} amount={amount} currency=INR duration_ms={dur} region={region} workflow_step=initiate error=upstream_auth_failure error_code=TXN_FAILED trace_id={tid} correlation_id=CHAOS-{cid}',
]

TIERS   = ["HNI", "Corporate", "Retail"]
REGIONS = ["HYD", "MUM", "BLR", "DEL"]

def send_hec(hec_url, token, line):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    payload = f"{now} ERROR {line}"
    resp = requests.post(
        f"{hec_url}/services/collector/raw",
        headers={"Authorization": f"Splunk {token}", "Content-Type": "text/plain"},
        params={"index": INDEX, "sourcetype": SOURCETYPE},
        data=payload, verify=False, timeout=5
    )
    return resp.status_code

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hec-url", required=True)
    parser.add_argument("--token",   required=True)
    parser.add_argument("--count",   type=int, default=20, help="Number of chaos events to inject")
    args = parser.parse_args()

    print("🔥 CHAOS INJECTION STARTING — Auth service latency spike simulation")
    print(f"   Injecting {args.count} failure events...\n")

    for i in range(args.count):
        tier   = random.choice(TIERS)
        region = random.choice(REGIONS)
        uid    = random.randint(9000, 9999)
        amount = random.choice([50000, 150000, 250000, 500000, 1200000, 3500000])
        latency = random.randint(2500, 4000)
        tid    = f"chaos{random.randint(10000,99999)}"
        cid    = f"{i+1:04d}"

        auth_line = CHAOS_TEMPLATES[0].format(
            uid=uid, tier=tier, amount=amount,
            latency=latency, region=region, tid=tid, cid=cid
        )
        pay_line = CHAOS_TEMPLATES[1].format(
            uid=uid, tier=tier, amount=amount,
            dur=latency+150, region=region, tid=tid, cid=cid
        )

        s1 = send_hec(args.hec_url, args.token, auth_line)
        s2 = send_hec(args.hec_url, args.token, pay_line)
        print(f"  [{i+1:02d}] {tier:10s} ₹{amount:>10,} | latency={latency}ms | region={region} → HEC {s1}/{s2}")
        time.sleep(0.5)

    print(f"\n✅ Chaos injection complete. Check Splunk dashboard — KPIs should degrade now.")
    revenue = sum([50000,150000,250000,500000,1200000,3500000]) * (args.count // 6)
    print(f"   Estimated revenue injected at risk: ₹{revenue:,}")

if __name__ == "__main__":
    main()
