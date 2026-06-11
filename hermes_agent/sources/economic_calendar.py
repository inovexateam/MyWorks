"""
Hermes — Economic Calendar Auto-Sync
Pulls upcoming RBI/Fed/macro events automatically.
No more hardcoded dates.
"""

import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta

log = logging.getLogger("hermes.econ_calendar")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# Fallback static calendar (updated quarterly)
STATIC_CALENDAR = [
    {"event": "RBI MPC Meeting",          "date": "2026-08-05", "impact": "HIGH",   "country": "IN"},
    {"event": "RBI MPC Result",           "date": "2026-08-07", "impact": "HIGH",   "country": "IN"},
    {"event": "US Fed FOMC Meeting",      "date": "2026-07-28", "impact": "HIGH",   "country": "US"},
    {"event": "US Fed FOMC Decision",     "date": "2026-07-30", "impact": "HIGH",   "country": "US"},
    {"event": "India CPI Inflation",      "date": "2026-07-14", "impact": "MEDIUM", "country": "IN"},
    {"event": "India IIP Data",           "date": "2026-07-11", "impact": "MEDIUM", "country": "IN"},
    {"event": "India GDP Q1 FY27",        "date": "2026-08-28", "impact": "HIGH",   "country": "IN"},
    {"event": "US Non-Farm Payroll",      "date": "2026-07-02", "impact": "HIGH",   "country": "US"},
    {"event": "US CPI Inflation",         "date": "2026-07-15", "impact": "HIGH",   "country": "US"},
    {"event": "RBI MPC Meeting",          "date": "2026-10-06", "impact": "HIGH",   "country": "IN"},
    {"event": "Union Budget FY28",        "date": "2027-02-01", "impact": "HIGH",   "country": "IN"},
]


def _fetch_investing_calendar() -> list:
    """
    Try to pull economic calendar from investing.com.
    Falls back to static if blocked.
    """
    events = []
    try:
        url = "https://in.investing.com/economic-calendar/"
        r   = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", id="economicCalendarData")
        if not table:
            return []
        today = date.today()
        for row in table.find_all("tr", class_=lambda c: c and "js-event-item" in c)[:30]:
            try:
                impact_td = row.find("td", class_="sentiment")
                n_bulls   = len(impact_td.find_all("i", class_="grayFullBullishIcon")) if impact_td else 0
                impact    = "HIGH" if n_bulls >= 3 else ("MEDIUM" if n_bulls >= 2 else "LOW")
                event_td  = row.find("td", class_="event")
                event_name= event_td.get_text(strip=True) if event_td else ""
                date_td   = row.get("data-event-datetime","")
                if date_td:
                    ev_date = datetime.strptime(date_td[:10], "%Y/%m/%d").date()
                    if ev_date >= today:
                        events.append({
                            "event":   event_name[:60],
                            "date":    str(ev_date),
                            "impact":  impact,
                            "country": "GLOBAL",
                        })
            except Exception:
                continue
    except Exception as e:
        log.debug(f"Investing calendar fetch failed: {e}")
    return events


def get_upcoming_events(days_ahead: int = 30) -> list:
    """
    Get upcoming economic events, sorted by date.
    Tries live fetch first, falls back to static.
    """
    today    = date.today()
    end_date = today + timedelta(days=days_ahead)

    # Try live first
    live = _fetch_investing_calendar()
    if live:
        log.info(f"Fetched {len(live)} live calendar events.")
        source = live
    else:
        log.info("Using static calendar fallback.")
        source = STATIC_CALENDAR

    results = []
    for ev in source:
        try:
            ev_date  = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            if today <= ev_date <= end_date:
                days_out = (ev_date - today).days
                results.append({
                    **ev,
                    "ev_date":  ev_date,
                    "days_out": days_out,
                    "urgent":   days_out <= 3,
                    "this_week": days_out <= 7,
                })
        except Exception:
            continue

    results.sort(key=lambda x: x["days_out"])
    return results


def get_high_impact_events(days_ahead: int = 7) -> list:
    return [e for e in get_upcoming_events(days_ahead) if e["impact"] in ("HIGH","MEDIUM")]
