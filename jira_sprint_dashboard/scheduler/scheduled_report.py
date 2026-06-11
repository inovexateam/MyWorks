"""
Scheduler - runs as a background process / service.
Fetches sprint data, generates charts, and emails the report
on a configured schedule (e.g., daily at 9 AM).

Usage:
    python scheduler/scheduled_report.py            # run scheduler loop
    python scheduler/scheduled_report.py --now      # send report immediately, once
"""
import os
import sys
import time
import argparse
import schedule
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.jira_client import JiraClient
from core import report
from core.emailer import send_sprint_report_email

load_dotenv()


def run_report_job():
    print(f"[{datetime.now()}] Running sprint report job...")
    try:
        board_id = int(os.environ["JIRA_BOARD_ID"])
        sp_field = os.environ.get("JIRA_STORY_POINTS_FIELD", "customfield_10016")

        client = JiraClient()
        data = report.fetch_and_compute(board_id, sp_field, client)

        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "_scheduled")
        chart_paths = report.generate_charts(data, out_dir, dark=False)  # light theme for email

        html = report.summary_html_table(data)
        send_sprint_report_email(chart_paths, html, data.sprint["name"])

        print(f"[{datetime.now()}] Report sent successfully for sprint '{data.sprint['name']}'.")
    except Exception as e:
        print(f"[{datetime.now()}] ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(description="JIRA Sprint Report Scheduler")
    parser.add_argument("--now", action="store_true", help="Run the report job once immediately and exit.")
    parser.add_argument("--time", default=os.environ.get("REPORT_SCHEDULE_TIME", "09:00"),
                         help="Daily time to send report, HH:MM 24h format (default 09:00).")
    parser.add_argument("--days", default=os.environ.get("REPORT_SCHEDULE_DAYS", "mon,tue,wed,thu,fri"),
                         help="Comma-separated days to send (default mon-fri).")
    args = parser.parse_args()

    if args.now:
        run_report_job()
        return

    days = [d.strip().lower() for d in args.days.split(",")]
    day_methods = {
        "mon": schedule.every().monday, "tue": schedule.every().tuesday,
        "wed": schedule.every().wednesday, "thu": schedule.every().thursday,
        "fri": schedule.every().friday, "sat": schedule.every().saturday,
        "sun": schedule.every().sunday,
    }
    for d in days:
        if d in day_methods:
            day_methods[d].at(args.time).do(run_report_job)

    print(f"Scheduler started. Will send report at {args.time} on: {', '.join(days)}")
    print("Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
