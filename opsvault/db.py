import sqlite3, os, json
from datetime import datetime

DB_PATH = os.path.join(os.path.expanduser("~"), "opsvault.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    url TEXT DEFAULT '',
    folder TEXT DEFAULT '',
    env TEXT DEFAULT 'PROD',
    priority TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    date TEXT,
    due TEXT DEFAULT '',
    remind INTEGER DEFAULT 15,
    done INTEGER DEFAULT 0,
    created TEXT,
    updated TEXT
);
CREATE TABLE IF NOT EXISTS folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#5b7fff'
);
CREATE TABLE IF NOT EXISTS health (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'ok',
    uptime TEXT DEFAULT '100%',
    latency TEXT DEFAULT '—'
);
CREATE TABLE IF NOT EXISTS oncall (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team TEXT, name TEXT, phone TEXT, shift TEXT
);
CREATE TABLE IF NOT EXISTS sla (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, target REAL, actual REAL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, value TEXT
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    # Seed if empty
    if conn.execute("SELECT COUNT(*) FROM folders").fetchone()[0] == 0:
        seed_data(conn)
    conn.close()

def seed_data(conn):
    folders = [
        ("fp","Payments","#c8a84b"), ("fc","Core Banking","#7aaef5"),
        ("fa","API Gateway","#5fd496"), ("fau","Auth & Identity","#a584e0"),
        ("fr","Risk & Fraud","#ff7070"), ("fi","Cloud Infra","#f0a84a"),
        ("fs","Security","#e05252"), ("fd","Data Platform","#4ed4c4"),
        ("fme","Personal","#8892aa"),
    ]
    conn.executemany("INSERT INTO folders VALUES(?,?,?)", folders)

    health = [
        ("h1","Payment Gateway","ok","99.97%","42ms"),
        ("h2","Core Banking API","ok","99.99%","18ms"),
        ("h3","Auth Service","warn","99.85%","210ms"),
        ("h4","Fraud Detection","ok","100%","8ms"),
        ("h5","Kafka Cluster","ok","99.99%","5ms"),
        ("h6","Redis Cache","ok","100%","1ms"),
        ("h7","Oracle DB Primary","ok","100%","12ms"),
        ("h8","Oracle DB Secondary","warn","98.2%","890ms"),
        ("h9","NEFT/RTGS Bridge","crit","97.1%","2100ms"),
        ("h10","SWIFT Connector","ok","99.95%","55ms"),
        ("h11","Mobile Banking API","ok","99.88%","95ms"),
    ]
    conn.executemany("INSERT INTO health VALUES(?,?,?,?,?)", health)

    oncall = [
        ("Payments","Ravi Kumar","+91-98000-11111","24h"),
        ("Core Banking","Priya Sharma","+91-98000-22222","24h"),
        ("API Gateway","Arun Mehta","+91-98000-33333","24h"),
        ("Auth & Identity","Sneha Reddy","+91-98000-44444","Night"),
        ("Cloud Infra","Vikram Singh","+91-98000-55555","24h"),
        ("Security","Deepa Nair","+91-98000-66666","24h"),
    ]
    conn.executemany("INSERT INTO oncall(team,name,phone,shift) VALUES(?,?,?,?)", oncall)

    sla_data = [
        ("Payment Success Rate", 99.9, 99.97),
        ("Auth Response < 200ms", 99.5, 98.85),
        ("API Availability", 99.95, 99.99),
        ("NEFT Processing SLA", 98.0, 97.1),
        ("Fraud Detection Latency", 99.0, 99.62),
        ("Core Banking Uptime", 99.99, 100.0),
    ]
    conn.executemany("INSERT INTO sla(name,target,actual) VALUES(?,?,?)", sla_data)

    import uuid
    now = datetime.now().isoformat()
    today = datetime.now().strftime("%Y-%m-%d")
    items = [
        ("incident","P1 — NEFT Processing Latency > 2s","NEFT bridge 2100ms avg. War room active.","","fp","PROD","P1 — Critical","neft,p1,latency"),
        ("snow","INC0091234 — Auth Service Slow Response","Auth averaging 210ms. SLA breach risk.","","fau","PROD","P2 — High","auth,snow"),
        ("change","TCI-2891 — Oracle DB Patching 19.21","Change window: Saturday 01:00–04:00 IST. CAB approved.","","fi","PROD","P3 — Medium","oracle,tci"),
        ("splunk","Payment Gateway Error Rate — Last 1h","index=payments_prod level=ERROR | stats count by host, error_code | sort -count","https://splunk.internal/search","fp","PROD","","splunk,payments"),
        ("splunk","Auth Token Failures","index=auth_prod event_type=TOKEN_FAILURE | timechart span=5m count by reason","https://splunk.internal/auth","fau","PROD","","splunk,auth"),
        ("grafana","K8s Cluster PROD Dashboard","CPU, memory, pod restarts across all namespaces","https://grafana.internal/d/k8s-prod","fi","PROD","","grafana,k8s"),
        ("runbook","NEFT Bridge Failover","1. Alert NOC\n2. Check SWIFT health\n3. Run /opt/neft/failover.sh\n4. Validate queue drain\n5. Escalate L3 if >15min","","fp","PROD","","runbook,neft"),
        ("runbook","P1 Incident Response SOP","1. Acknowledge <5min\n2. Create war room\n3. Assign IC + Comms\n4. Update status page\n5. RCA within 48h","","fme","","","runbook,p1"),
        ("jira","PAYMENTS-2341 — RTGS retry logic","P2 Sprint 42. Retry on 504 with exponential backoff.","https://jira.internal/PAYMENTS-2341","fp","PROD","P2 — High","jira,rtgs"),
        ("compliance","PCI-DSS — Quarterly Access Review","Review all privileged access on PROD. Submit to CISO by EOM.","","fs","","P2 — High","pci,compliance"),
        ("contact","Vikram Singh — Infra Lead","Phone: +91-98000-55555\nSlack: @vikram.singh","","fi","","","contact,infra"),
        ("todo","Update NEFT runbook with new failover IP","Old IP still in runbook. Changed 2024-11-01.","","fme","","P2 — High","todo,runbook"),
        ("todo","Raise CAB for Oracle patch Saturday","","","fi","","P3 — Medium","todo,change"),
        ("note","Post-mortem: Auth degradation 2024-10-28","RCA: JVM heap exhaustion on auth-pod-3.\nFix: heap → 4GB. Actions: add heap alert.","","fau","","","postmortem,auth"),
        ("link","Confluence — Payments Architecture","","https://confluence.internal/payments-arch","fp","","","docs,arch"),
    ]
    for t,title,body,url,folder,env,priority,tags in items:
        conn.execute(
            "INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()),t,title,body,url,folder,env,priority,
             json.dumps(tags.split(",") if tags else []),
             today,"",15,0,now,now)
        )
    conn.commit()

# ── CRUD ──────────────────────────────────
def get_items(type_filter=None, folder_filter=None, env_filter=None, search=None):
    conn = get_conn()
    q = "SELECT * FROM items WHERE 1=1"
    params = []
    if type_filter: q += " AND type=?"; params.append(type_filter)
    if folder_filter: q += " AND folder=?"; params.append(folder_filter)
    if env_filter: q += " AND env=?"; params.append(env_filter)
    if search:
        q += " AND (title LIKE ? OR body LIKE ? OR url LIKE ? OR tags LIKE ?)"
        s = f"%{search}%"
        params.extend([s,s,s,s])
    q += " ORDER BY created DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_item(id):
    conn = get_conn()
    r = conn.execute("SELECT * FROM items WHERE id=?", (id,)).fetchone()
    conn.close()
    return dict(r) if r else None

def save_item(item):
    conn = get_conn()
    item['updated'] = datetime.now().isoformat()
    if isinstance(item.get('tags'), list):
        item['tags'] = json.dumps(item['tags'])
    if 'created' not in item or not item['created']:
        item['created'] = item['updated']
    conn.execute("""INSERT OR REPLACE INTO items
        (id,type,title,body,url,folder,env,priority,tags,date,due,remind,done,created,updated)
        VALUES(:id,:type,:title,:body,:url,:folder,:env,:priority,:tags,:date,:due,:remind,:done,:created,:updated)""", item)
    conn.commit(); conn.close()

def delete_item(id):
    conn = get_conn()
    conn.execute("DELETE FROM items WHERE id=?", (id,)); conn.commit(); conn.close()

def toggle_done(id):
    conn = get_conn()
    conn.execute("UPDATE items SET done=NOT done, updated=? WHERE id=?", (datetime.now().isoformat(), id))
    conn.commit(); conn.close()

def get_folders(): 
    conn = get_conn()
    r = conn.execute("SELECT * FROM folders ORDER BY name").fetchall()
    conn.close()
    return [dict(x) for x in r]

def get_health():
    conn = get_conn()
    r = conn.execute("SELECT * FROM health").fetchall()
    conn.close()
    return [dict(x) for x in r]

def set_health_status(id, status):
    conn = get_conn()
    conn.execute("UPDATE health SET status=? WHERE id=?", (status, id))
    conn.commit(); conn.close()

def get_oncall():
    conn = get_conn()
    r = conn.execute("SELECT * FROM oncall").fetchall()
    conn.close()
    return [dict(x) for x in r]

def get_sla():
    conn = get_conn()
    r = conn.execute("SELECT * FROM sla").fetchall()
    conn.close()
    return [dict(x) for x in r]

def get_setting(key, default=""):
    conn = get_conn()
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return r[0] if r else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))
    conn.commit(); conn.close()
