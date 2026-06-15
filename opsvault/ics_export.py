import os, json
from datetime import datetime, timedelta

def ics_dt(dt_str):
    """Convert datetime string to ICS UTC format."""
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str)
        else:
            dt = datetime.fromisoformat(dt_str + "T09:00:00")
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except:
        return datetime.now().strftime("%Y%m%dT%H%M%SZ")

def build_ics(items):
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//OpsVault//Banking Ops//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    ]
    for it in items:
        due = it.get('due') or (it.get('date','') + 'T09:00')
        if not due.strip(): continue
        start = ics_dt(due)
        try:
            end_dt = datetime.fromisoformat(due if 'T' in due else due + 'T09:00')
            end_dt += timedelta(minutes=30)
            end = end_dt.strftime("%Y%m%dT%H%M%SZ")
        except:
            end = start
        remind = int(it.get('remind') or 15)
        tags = it.get('tags','[]')
        if isinstance(tags, str):
            try: tags = json.loads(tags)
            except: tags = []
        summary = ((it.get('priority','').split(' ')[0]+' — ') if it.get('priority') else '') + it.get('title','')
        desc = (it.get('body','') or it.get('url','') or '').replace('\n','\\n').replace(',','\\,')[:500]
        def esc(s): return str(s).replace(',','\\,').replace(';','\\;').replace('\n','\\n')
        lines += [
            "BEGIN:VEVENT",
            f"UID:{it['id']}@opsvault",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            f"SUMMARY:{esc(summary)}",
            f"DESCRIPTION:{esc(desc)}",
            f"CATEGORIES:{it.get('type','').upper()}",
        ]
        if it.get('url'): lines.append(f"URL:{it['url']}")
        lines += [
            "BEGIN:VALARM",
            f"TRIGGER:-PT{remind}M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:OpsVault Reminder — {esc(summary[:60])}",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)

def export_ics(items, path=None):
    """Write ICS file and return path. Opens with default handler (Outlook)."""
    content = build_ics(items)
    if not path:
        path = os.path.join(os.path.expanduser("~"), "opsvault_export.ics")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path

def open_in_outlook(path):
    """Open .ics with default handler — Outlook on Windows."""
    import subprocess, sys
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])
