#!/usr/bin/env python3
"""
feedback.py — Manage feedback-log.json for the Design Flaw Reviewer agent.

This lets you record which flagged "design flaws" were accepted, rejected,
or deferred, with a reason. Future reviews (via the agentic chat mode) read
this log and skip re-reporting previously-rejected items at the same
location.

Usage:
    # Add an entry
    python3 feedback.py add \
        --title "OrderService injects concrete SmtpClient" \
        --location "src/Services/OrderService.cs:42" \
        --category "DIP violation" \
        --decision rejected \
        --reason "Intentional - see ADR-007, email is mocked via test seam"

    # List all entries
    python3 feedback.py list

    # List only rejected (things future reviews should skip)
    python3 feedback.py list --decision rejected

    # Show summary stats (acceptance rate per category)
    python3 feedback.py stats
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date

LOG_FILE = "feedback-log.json"


def load_log(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return []


def save_log(path, entries):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)


def cmd_add(args):
    entries = load_log(args.file)
    entry = {
        "date": args.date or date.today().isoformat(),
        "flaw_title": args.title,
        "location": args.location,
        "category": args.category,
        "decision": args.decision,
        "reason": args.reason or "",
    }
    entries.append(entry)
    save_log(args.file, entries)
    print(f"Added entry: {entry['flaw_title']} -> {entry['decision']}")


def cmd_list(args):
    entries = load_log(args.file)
    if args.decision:
        entries = [e for e in entries if e["decision"] == args.decision]
    if not entries:
        print("(no entries)")
        return
    for e in entries:
        print(f"[{e['date']}] {e['decision'].upper():9s} {e['location']:40s} {e['flaw_title']}")
        if e.get("reason"):
            print(f"           reason: {e['reason']}")


def cmd_stats(args):
    entries = load_log(args.file)
    if not entries:
        print("(no entries)")
        return

    by_decision = Counter(e["decision"] for e in entries)
    by_category = defaultdict(lambda: Counter())
    for e in entries:
        by_category[e["category"]][e["decision"]] += 1

    print("Overall:")
    total = len(entries)
    for decision, count in by_decision.most_common():
        print(f"  {decision:10s}: {count:3d}  ({count/total:.0%})")

    print("\nBy category:")
    for category, counter in by_category.items():
        cat_total = sum(counter.values())
        accepted = counter.get("accepted", 0)
        print(f"  {category:35s} accepted {accepted}/{cat_total} "
              f"({accepted/cat_total:.0%})")

    print("\nCategories with low acceptance (consider tuning chat mode "
          "instructions to reduce false positives):")
    for category, counter in by_category.items():
        cat_total = sum(counter.values())
        accepted = counter.get("accepted", 0)
        if cat_total >= 3 and accepted / cat_total < 0.5:
            print(f"  - {category} ({accepted}/{cat_total} accepted)")


def main():
    parser = argparse.ArgumentParser(description="Manage design review feedback log")
    parser.add_argument("--file", default=LOG_FILE, help="Path to feedback log JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a feedback entry")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--location", required=True)
    p_add.add_argument("--category", required=True)
    p_add.add_argument("--decision", required=True, choices=["accepted", "rejected", "deferred"])
    p_add.add_argument("--reason", default="")
    p_add.add_argument("--date", default=None)
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List feedback entries")
    p_list.add_argument("--decision", choices=["accepted", "rejected", "deferred"])
    p_list.set_defaults(func=cmd_list)

    p_stats = sub.add_parser("stats", help="Show acceptance-rate stats")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
