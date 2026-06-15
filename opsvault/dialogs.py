import uuid, json
from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtGui import QFont

TYPES = ["link","note","todo","incident","change","splunk","jira","snow","tci","grafana","runbook","alert","oncall","sla","compliance","contact","custom"]
TYPE_EMOJI = {"link":"🔗","note":"📝","todo":"☐","incident":"🚨","change":"🔄","splunk":"🔍","jira":"🎫","snow":"🎧","tci":"⚙️","grafana":"📊","runbook":"📋","alert":"🔔","oncall":"📱","sla":"📈","compliance":"🛡️","contact":"👤","custom":"✦"}
PRIORITY = ["","P1 — Critical","P2 — High","P3 — Medium","P4 — Low"]
ENVS = ["PROD","UAT","DEV",""]

def label(text):
    l = QLabel(text.upper())
    l.setObjectName("fieldLabel")
    return l

class ItemDialog(QDialog):
    def __init__(self, parent, folders, item=None):
        super().__init__(parent)
        self.folders = folders
        self.item = item or {}
        self.setWindowTitle("Edit Item" if item else "Add Item")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10); lay.setContentsMargins(20,20,20,20)

        # Title
        h = QLabel("Edit Item" if self.item.get('id') else "Add Item")
        h.setStyleSheet("font-size:15px;font-weight:500;color:#dde1eb;margin-bottom:4px;")
        lay.addWidget(h)

        # Type selector
        lay.addWidget(label("Type"))
        self.type_combo = QComboBox()
        for t in TYPES:
            self.type_combo.addItem(f"{TYPE_EMOJI.get(t,'✦')} {t.upper()}", t)
        if self.item.get('type'):
            idx = TYPES.index(self.item['type']) if self.item['type'] in TYPES else 0
            self.type_combo.setCurrentIndex(idx)
        lay.addWidget(self.type_combo)

        # Title
        lay.addWidget(label("Title / URL / Ticket ID"))
        self.title_edit = QLineEdit(self.item.get('title',''))
        self.title_edit.setPlaceholderText("Paste URL, INC0001, TCI-123, or title…")
        self.title_edit.textChanged.connect(self._auto_detect)
        lay.addWidget(self.title_edit)

        # Body
        lay.addWidget(label("Body / Query / Notes"))
        self.body_edit = QTextEdit()
        self.body_edit.setPlainText(self.item.get('body',''))
        self.body_edit.setPlaceholderText("Splunk query, runbook steps, notes…")
        self.body_edit.setMaximumHeight(100)
        lay.addWidget(self.body_edit)

        # URL
        lay.addWidget(label("URL"))
        self.url_edit = QLineEdit(self.item.get('url',''))
        self.url_edit.setPlaceholderText("https://…")
        lay.addWidget(self.url_edit)

        # Row: Date + Env
        row1 = QHBoxLayout()
        l1 = QVBoxLayout()
        l1.addWidget(label("Date"))
        self.date_edit = QLineEdit(self.item.get('date', datetime.now().strftime('%Y-%m-%d')))
        self.date_edit.setPlaceholderText("YYYY-MM-DD")
        l1.addWidget(self.date_edit)
        l2 = QVBoxLayout()
        l2.addWidget(label("Environment"))
        self.env_combo = QComboBox()
        for e in ENVS: self.env_combo.addItem(e or "—", e)
        ev = self.item.get('env','PROD')
        if ev in ENVS: self.env_combo.setCurrentIndex(ENVS.index(ev))
        l2.addWidget(self.env_combo)
        row1.addLayout(l1); row1.addLayout(l2)
        lay.addLayout(row1)

        # Row: Folder + Priority
        row2 = QHBoxLayout()
        l3 = QVBoxLayout()
        l3.addWidget(label("Team / Folder"))
        self.folder_combo = QComboBox()
        for f in self.folders: self.folder_combo.addItem(f['name'], f['id'])
        fid = self.item.get('folder','')
        fids = [f['id'] for f in self.folders]
        if fid in fids: self.folder_combo.setCurrentIndex(fids.index(fid))
        l3.addWidget(self.folder_combo)
        l4 = QVBoxLayout()
        l4.addWidget(label("Priority"))
        self.prio_combo = QComboBox()
        for p in PRIORITY: self.prio_combo.addItem(p or "—", p)
        pr = self.item.get('priority','')
        if pr in PRIORITY: self.prio_combo.setCurrentIndex(PRIORITY.index(pr))
        l4.addWidget(self.prio_combo)
        row2.addLayout(l3); row2.addLayout(l4)
        lay.addLayout(row2)

        # Tags
        lay.addWidget(label("Tags (comma separated)"))
        tags = self.item.get('tags','[]')
        if isinstance(tags, str):
            try: tags = json.loads(tags)
            except: tags = []
        self.tags_edit = QLineEdit(', '.join(tags))
        self.tags_edit.setPlaceholderText("prod, payments, critical")
        lay.addWidget(self.tags_edit)

        # Due datetime + remind
        row3 = QHBoxLayout()
        l5 = QVBoxLayout()
        l5.addWidget(label("⏰ Due Date & Time (Outlook Reminder)"))
        self.due_edit = QLineEdit(self.item.get('due',''))
        self.due_edit.setPlaceholderText("YYYY-MM-DDTHH:MM  e.g. 2024-11-20T14:30")
        l5.addWidget(self.due_edit)
        l6 = QVBoxLayout()
        l6.addWidget(label("Remind Before"))
        self.remind_combo = QComboBox()
        for v,t in [('15','15 minutes'),('60','1 hour'),('1440','1 day'),('2880','2 days')]:
            self.remind_combo.addItem(t, v)
        rv = str(self.item.get('remind','15'))
        rvals = ['15','60','1440','2880']
        if rv in rvals: self.remind_combo.setCurrentIndex(rvals.index(rv))
        l6.addWidget(self.remind_combo)
        row3.addLayout(l5); row3.addLayout(l6)
        lay.addLayout(row3)

        # Footer
        lay.addSpacing(6)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#1a1e2a;")
        lay.addWidget(sep)
        foot = QHBoxLayout()
        foot.addStretch()
        cancel = QPushButton("Cancel"); cancel.setObjectName("btnSecondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save Item"); save.setObjectName("btnPrimary")
        save.clicked.connect(self.accept)
        save.setDefault(True)
        foot.addWidget(cancel); foot.addWidget(save)
        lay.addLayout(foot)

    def _auto_detect(self, text):
        """Auto-detect type from URL/ticket patterns."""
        t = text.strip()
        detected = None
        if t.startswith('http'):
            if 'splunk' in t: detected='splunk'
            elif 'jira' in t or 'atlassian' in t: detected='jira'
            elif 'servicenow' in t or 'snow.' in t: detected='snow'
            elif 'grafana' in t: detected='grafana'
            elif 'confluence' in t or 'wiki' in t: detected='runbook'
            else: detected='link'
            self.url_edit.setText(t)
        elif t.upper().startswith(('INC','CHG','REQ','RITM')): detected='snow'
        elif t.upper().startswith('TCI-'): detected='tci'
        elif len(t)>3 and '-' in t and t.split('-')[0].isupper(): detected='jira'
        if detected and detected in TYPES:
            self.type_combo.setCurrentIndex(TYPES.index(detected))

    def get_data(self):
        tags_raw = [x.strip() for x in self.tags_edit.text().split(',') if x.strip()]
        return {
            'id': self.item.get('id') or str(uuid.uuid4()),
            'type': self.type_combo.currentData(),
            'title': self.title_edit.text().strip(),
            'body': self.body_edit.toPlainText().strip(),
            'url': self.url_edit.text().strip(),
            'date': self.date_edit.text().strip() or datetime.now().strftime('%Y-%m-%d'),
            'env': self.env_combo.currentData() or '',
            'folder': self.folder_combo.currentData() or '',
            'priority': self.prio_combo.currentData() or '',
            'tags': json.dumps(tags_raw),
            'due': self.due_edit.text().strip(),
            'remind': int(self.remind_combo.currentData() or 15),
            'done': self.item.get('done', 0),
            'created': self.item.get('created') or datetime.now().isoformat(),
        }
