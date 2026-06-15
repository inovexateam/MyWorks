import json
from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QCursor

TYPE_COLOR = {
    "link":"#7aaef5","note":"#4ed4c4","todo":"#f0a84a","incident":"#ff7070",
    "change":"#a584e0","splunk":"#a584e0","jira":"#7aaef5","snow":"#5fd496",
    "tci":"#f0a84a","grafana":"#e2c97e","runbook":"#4ed4c4","alert":"#ff7070",
    "oncall":"#e2c97e","sla":"#5fd496","compliance":"#a584e0","contact":"#4ed4c4","custom":"#8892aa",
}
TYPE_EMOJI = {"link":"🔗","note":"📝","todo":"☐","incident":"🚨","change":"🔄","splunk":"🔍",
    "jira":"🎫","snow":"🎧","tci":"⚙️","grafana":"📊","runbook":"📋","alert":"🔔",
    "oncall":"📱","sla":"📈","compliance":"🛡️","contact":"👤","custom":"✦"}

def fmt_date(ds):
    if not ds: return ''
    try:
        d = datetime.fromisoformat(ds[:10])
        delta = (datetime.now().date() - d.date()).days
        if delta == 0: return 'today'
        if delta == 1: return 'yesterday'
        if delta < 7: return f'{delta}d ago'
        if delta < 30: return f'{delta//7}w ago'
        return d.strftime('%d %b')
    except: return ds[:10]

def parse_tags(tags):
    if isinstance(tags, list): return tags
    try: return json.loads(tags) if tags else []
    except: return []

class CardWidget(QFrame):
    clicked = pyqtSignal(dict)
    edit_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(str)
    toggle_done = pyqtSignal(str)
    outlook_requested = pyqtSignal(dict)

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("cardWidget")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._build()

    def _build(self):
        it = self.item
        tc = TYPE_COLOR.get(it.get('type','custom'), '#8892aa')
        is_overdue = bool(it.get('due') and not it.get('done') and datetime.fromisoformat(it['due']) < datetime.now()) if it.get('due') else False

        # Top accent line
        self.setStyleSheet(f"""
            #cardWidget {{
                background:#111318;
                border:1px solid {'#3a0f0f' if is_overdue else '#1a1e2a'};
                border-top:2px solid {tc};
                border-radius:10px;
                padding:12px 14px;
            }}
            #cardWidget:hover {{ background:#181c26; border-color:{'#5a1f1f' if is_overdue else '#1f2432'}; }}
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(5); lay.setContentsMargins(0,0,0,0)

        # Type badge row
        top_row = QHBoxLayout()
        type_lbl = QLabel(f"{TYPE_EMOJI.get(it.get('type',''),'✦')} {it.get('type','').upper()}{(' · '+it['priority'].split(' ')[0]) if it.get('priority') else ''}")
        type_lbl.setObjectName("typeLabel")
        type_lbl.setStyleSheet(f"color:{tc};font-family:'Consolas';font-size:9px;font-weight:bold;letter-spacing:1px;")
        top_row.addWidget(type_lbl)
        top_row.addStretch()

        # Action buttons (shown on hover via CSS opacity trick — use small btns)
        if it.get('type') == 'todo':
            done_btn = QPushButton("↺" if it.get('done') else "✓")
            done_btn.setFixedSize(22, 22)
            done_btn.setStyleSheet("background:#1f2432;border:1px solid #262d3d;border-radius:4px;color:#4a5470;font-size:10px;")
            done_btn.clicked.connect(lambda: self.toggle_done.emit(it['id']))
            top_row.addWidget(done_btn)
        edit_btn = QPushButton("✎"); edit_btn.setFixedSize(22,22)
        edit_btn.setStyleSheet("background:#1f2432;border:1px solid #262d3d;border-radius:4px;color:#4a5470;font-size:10px;")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(it))
        del_btn = QPushButton("✕"); del_btn.setFixedSize(22,22)
        del_btn.setStyleSheet("background:#1f2432;border:1px solid #262d3d;border-radius:4px;color:#4a5470;font-size:10px;")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(it['id']))
        top_row.addWidget(edit_btn); top_row.addWidget(del_btn)
        lay.addLayout(top_row)

        # Title
        title = it.get('title','')
        title_lbl = QLabel(title)
        title_lbl.setObjectName("cardTitle")
        title_lbl.setWordWrap(True)
        if it.get('done'):
            title_lbl.setStyleSheet("font-size:13px;font-weight:500;color:#4a5470;text-decoration:line-through;")
        lay.addWidget(title_lbl)

        # Body
        body = it.get('body','')
        if body and body != title:
            body_lbl = QLabel(body[:130] + ('…' if len(body)>130 else ''))
            body_lbl.setObjectName("cardBody")
            body_lbl.setWordWrap(True)
            lay.addWidget(body_lbl)

        # URL
        url = it.get('url','')
        if url:
            url_lbl = QLabel(f"↗ {url[:55]}{'…' if len(url)>55 else ''}")
            url_lbl.setObjectName("cardUrl")
            url_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            url_lbl.mousePressEvent = lambda e: __import__('webbrowser').open(url)
            lay.addWidget(url_lbl)

        # Footer: tags + date
        foot = QHBoxLayout(); foot.setSpacing(4)

        if is_overdue:
            ol = QLabel("⏰ OVERDUE"); ol.setObjectName("overdueTag"); foot.addWidget(ol)
        elif it.get('due'):
            due_str = it['due'][:16].replace('T',' ')
            dl = QLabel(f"⏰ {due_str}"); dl.setObjectName("dueTag"); foot.addWidget(dl)

        env = it.get('env','')
        if env:
            ec = {'PROD':'#ff7070','UAT':'#f0a84a','DEV':'#5fd496'}.get(env,'#4a5470')
            el = QLabel(env)
            el.setStyleSheet(f"background:rgba(0,0,0,.3);color:{ec};font-family:'Consolas';font-size:9px;padding:2px 6px;border-radius:2px;")
            foot.addWidget(el)

        for tag in parse_tags(it.get('tags'))[:3]:
            tl = QLabel(tag); tl.setObjectName("tag"); foot.addWidget(tl)

        foot.addStretch()
        date_lbl = QLabel(fmt_date(it.get('date','')))
        date_lbl.setObjectName("cardMeta")
        foot.addWidget(date_lbl)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#1a1e2a;margin:4px 0;")
        lay.addWidget(sep)
        lay.addLayout(foot)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item)
        super().mousePressEvent(e)


class CardGrid(QScrollArea):
    item_clicked = pyqtSignal(dict)
    item_edit = pyqtSignal(dict)
    item_delete = pyqtSignal(str)
    item_toggle = pyqtSignal(str)
    item_outlook = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(0,0,0,0)
        self.setWidget(self._container)
        self._cols = 3

    def load(self, items):
        # Clear
        while self._grid.count():
            w = self._grid.takeAt(0).widget()
            if w: w.deleteLater()
        if not items:
            empty = QLabel("No items yet.\nUse the capture bar above to add something.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color:#2e3550;font-size:14px;padding:60px;")
            self._grid.addWidget(empty, 0, 0, 1, self._cols)
            return
        for i, it in enumerate(items):
            card = CardWidget(it)
            card.clicked.connect(self.item_clicked)
            card.edit_requested.connect(self.item_edit)
            card.delete_requested.connect(self.item_delete)
            card.toggle_done.connect(self.item_toggle)
            card.outlook_requested.connect(self.item_outlook)
            self._grid.addWidget(card, i // self._cols, i % self._cols)
        # Spacer at bottom
        self._grid.setRowStretch(len(items)//self._cols + 1, 1)

    def resizeEvent(self, e):
        w = e.size().width()
        self._cols = max(1, w // 310)
        super().resizeEvent(e)


class StatBox(QFrame):
    def __init__(self, num, label, color="#dde1eb", parent=None):
        super().__init__(parent)
        self.setObjectName("statBox")
        self.setStyleSheet(f"#statBox{{background:#111318;border:1px solid #1a1e2a;border-top:2px solid {color};border-radius:10px;padding:14px 16px;}}")
        lay = QVBoxLayout(self)
        n = QLabel(str(num)); n.setObjectName("statNum")
        n.setStyleSheet(f"font-size:22px;font-weight:500;font-family:'Consolas';color:{color};")
        l = QLabel(label.upper()); l.setObjectName("statLabel")
        l.setStyleSheet("font-size:10px;color:#4a5470;letter-spacing:.4px;margin-top:4px;")
        lay.addWidget(n); lay.addWidget(l)


class HealthCard(QFrame):
    def __init__(self, h, parent=None):
        super().__init__(parent)
        self.setObjectName("healthCard")
        STATUS_COLOR = {'ok':'#3db87a','warn':'#d4812a','crit':'#e05252'}
        c = STATUS_COLOR.get(h.get('s') or h.get('status','ok'), '#4a5470')
        lay = QHBoxLayout(self); lay.setContentsMargins(12,10,12,10)
        dot = QLabel("●"); dot.setStyleSheet(f"color:{c};font-size:10px;")
        name = QLabel(h.get('name','')); name.setObjectName("healthName")
        val = QLabel(h.get('latency') or h.get('lat','—')); val.setObjectName("healthVal")
        lay.addWidget(dot); lay.addWidget(name,1); lay.addWidget(val)


class SectionHeader(QWidget):
    def __init__(self, text, count=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setContentsMargins(0,8,0,6)
        lbl = QLabel(text.upper())
        lbl.setStyleSheet("font-size:9px;font-weight:bold;color:#2e3550;letter-spacing:1px;font-family:'Consolas';")
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#1a1e2a;")
        lay.addWidget(lbl)
        if count is not None:
            cnt = QLabel(str(count))
            cnt.setStyleSheet("font-size:9px;color:#2e3550;font-family:'Consolas';margin-left:6px;")
            lay.addWidget(cnt)
        lay.addWidget(line, 1)
