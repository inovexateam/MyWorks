import sys, json, os
from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QColor, QAction, QKeySequence, QShortcut

import db, styles, dialogs, widgets, ics_export
from widgets import CardGrid, StatBox, HealthCard, SectionHeader, TYPE_COLOR, TYPE_EMOJI, parse_tags, fmt_date

# ── DETAIL PANEL ──────────────────────────
class DetailPanel(QWidget):
    closed = pyqtSignal()
    edit_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(str)
    toggle_done = pyqtSignal(str)
    outlook_export = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.item = None
        self.setFixedWidth(340)
        self.setObjectName("detailPanel")
        self.setStyleSheet("#detailPanel{background:#111318;border-left:1px solid #1a1e2a;}")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        # Top
        top = QWidget(); top.setStyleSheet("background:#111318;border-bottom:1px solid #1a1e2a;")
        tl = QVBoxLayout(top); tl.setContentsMargins(17,15,17,15)
        header_row = QHBoxLayout()
        self.type_lbl = QLabel(); self.type_lbl.setStyleSheet("font-size:9px;font-family:'Consolas';letter-spacing:.7px;")
        header_row.addWidget(self.type_lbl); header_row.addStretch()
        close_btn = QPushButton("✕"); close_btn.setFixedSize(26,26)
        close_btn.setStyleSheet("background:#1f2432;border:1px solid #262d3d;border-radius:6px;color:#4a5470;")
        close_btn.clicked.connect(self.closed.emit)
        header_row.addWidget(close_btn)
        tl.addLayout(header_row)
        self.title_lbl = QLabel(); self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet("font-size:14px;font-weight:500;color:#dde1eb;margin-top:5px;")
        tl.addWidget(self.title_lbl)
        self.prio_lbl = QLabel(); self.prio_lbl.setStyleSheet("font-size:10px;color:#f0a84a;font-family:'Consolas';margin-top:3px;")
        tl.addWidget(self.prio_lbl)
        self.date_lbl = QLabel(); self.date_lbl.setStyleSheet("font-size:10px;color:#4a5470;font-family:'Consolas';margin-top:2px;")
        tl.addWidget(self.date_lbl)
        lay.addWidget(top)

        # Body scroll
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); body.setStyleSheet("background:#111318;")
        self.body_lay = QVBoxLayout(body); self.body_lay.setContentsMargins(17,14,17,14); self.body_lay.setSpacing(12)
        self.body_lay.addStretch()
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        # Footer
        foot = QWidget(); foot.setStyleSheet("background:#111318;border-top:1px solid #1a1e2a;")
        fl = QHBoxLayout(foot); fl.setContentsMargins(14,10,14,10); fl.setSpacing(6)
        self.done_btn = QPushButton("✓ Done"); self.done_btn.setObjectName("btnSecondary")
        self.done_btn.clicked.connect(lambda: self.toggle_done.emit(self.item['id']))
        self.edit_btn = QPushButton("✎ Edit"); self.edit_btn.setObjectName("btnSecondary")
        self.edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.item))
        self.del_btn = QPushButton("✕ Delete"); self.del_btn.setObjectName("btnSecondary")
        self.del_btn.setObjectName("btnDanger"); self.del_btn.setProperty("class","btnDanger")
        self.del_btn.clicked.connect(lambda: self.delete_requested.emit(self.item['id']))
        self.outlook_btn = QPushButton("📅 Add to Outlook"); self.outlook_btn.setObjectName("btnOutlook")
        self.outlook_btn.clicked.connect(lambda: self.outlook_export.emit(self.item))
        self.open_btn = QPushButton("↗ Open URL"); self.open_btn.setObjectName("btnPrimary")
        self.open_btn.clicked.connect(self._open_url)
        fl.addWidget(self.done_btn); fl.addWidget(self.edit_btn); fl.addWidget(self.del_btn)
        fl.addStretch(); fl.addWidget(self.outlook_btn); fl.addWidget(self.open_btn)
        lay.addWidget(foot)

    def _field(self, label, value, monospace=False):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(3)
        lbl = QLabel(label.upper()); lbl.setObjectName("fieldLabel")
        val = QLabel(value); val.setWordWrap(True)
        val.setStyleSheet(f"font-size:12px;color:#8892aa;{'font-family:Consolas;' if monospace else ''}line-height:1.7;")
        l.addWidget(lbl); l.addWidget(val)
        return w

    def load(self, item):
        self.item = item
        tc = TYPE_COLOR.get(item.get('type','custom'),'#8892aa')
        self.type_lbl.setText(f"{TYPE_EMOJI.get(item.get('type',''),'✦')} {item.get('type','').upper()}{(' · '+item.get('env','')) if item.get('env') else ''}")
        self.type_lbl.setStyleSheet(f"font-size:9px;font-family:'Consolas';letter-spacing:.7px;color:{tc};")
        self.title_lbl.setText(item.get('title',''))
        self.prio_lbl.setText(item.get('priority',''))
        self.prio_lbl.setVisible(bool(item.get('priority')))
        self.date_lbl.setText(item.get('date',''))
        self.done_btn.setText("↺ Reopen" if item.get('done') else "✓ Done")
        self.done_btn.setVisible(item.get('type') == 'todo')
        self.open_btn.setVisible(bool(item.get('url')))

        # Due reminder info
        due_text = ""
        if item.get('due'):
            due_text = f"⏰ Due: {item['due'][:16].replace('T',' ')}  ·  Remind {item.get('remind',15)} min before"

        # Rebuild body
        while self.body_lay.count(): 
            w = self.body_lay.takeAt(0).widget()
            if w: w.deleteLater()

        if item.get('url'):
            self.body_lay.addWidget(self._field("URL", item['url'], True))
        if item.get('body'):
            self.body_lay.addWidget(self._field("Content", item['body']))
        if due_text:
            self.body_lay.addWidget(self._field("Reminder", due_text))
        folder = next((f for f in db.get_folders() if f['id']==item.get('folder')), None)
        if folder:
            self.body_lay.addWidget(self._field("Team / Folder", folder['name']))
        tags = parse_tags(item.get('tags','[]'))
        if tags:
            self.body_lay.addWidget(self._field("Tags", ', '.join(tags)))
        self.body_lay.addWidget(self._field("Created", fmt_date(item.get('created',''))))
        self.body_lay.addStretch()

    def _open_url(self):
        if self.item and self.item.get('url'):
            import webbrowser; webbrowser.open(self.item['url'])


# ── VIEWS ─────────────────────────────────
class HomeView(QScrollArea):
    item_clicked = pyqtSignal(dict)
    item_edit = pyqtSignal(dict)
    item_delete = pyqtSignal(str)
    item_toggle = pyqtSignal(str)
    item_outlook = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        self._w = QWidget(); self._lay = QVBoxLayout(self._w)
        self._lay.setContentsMargins(0,0,6,20); self._lay.setSpacing(6)
        self.setWidget(self._w)

    def _clear(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def _connect_grid(self, grid):
        grid.item_clicked.connect(self.item_clicked)
        grid.item_edit.connect(self.item_edit)
        grid.item_delete.connect(self.item_delete)
        grid.item_toggle.connect(self.item_toggle)
        grid.item_outlook.connect(self.item_outlook)

    def refresh(self):
        self._clear()
        items = db.get_items()
        health = db.get_health()
        crit = sum(1 for h in health if h.get('status','') == 'crit' or h.get('s','') == 'crit')
        warn = sum(1 for h in health if h.get('status','') == 'warn' or h.get('s','') == 'warn')
        inc = [i for i in items if i['type'] in ('incident','alert')]
        todos = [i for i in items if i['type']=='todo' and not i['done']]

        # Stats
        stat_row = QHBoxLayout()
        for num, lbl, col in [
            (len(inc), "Active Incidents", "#ff7070"),
            (crit+warn, "Degraded Services", "#f0a84a"),
            (sum(1 for i in items if i['type'] in ('change','tci')), "Change Requests", "#a584e0"),
            (sum(1 for i in items if i['type'] in ('splunk','grafana')), "Saved Queries", "#7aaef5"),
            (len(items), "Total Items", "#e2c97e"),
        ]:
            stat_row.addWidget(StatBox(num, lbl, col))
        self._lay.addLayout(stat_row)

        # Health mini
        self._lay.addWidget(SectionHeader("Service Health"))
        hgrid = QGridLayout(); hgrid.setSpacing(6)
        for i, h in enumerate(health[:6]):
            hgrid.addWidget(HealthCard(h), i//3, i%3)
        hw = QWidget(); hw.setLayout(hgrid)
        self._lay.addWidget(hw)

        # Incidents
        if inc:
            self._lay.addWidget(SectionHeader("Active Incidents", len(inc)))
            g = CardGrid(); g.load(inc[:4]); self._connect_grid(g)
            g.setFixedHeight(220); self._lay.addWidget(g)

        # Todos
        if todos:
            self._lay.addWidget(SectionHeader("My Open Todos", len(todos)))
            g2 = CardGrid(); g2.load(todos[:6]); self._connect_grid(g2)
            g2.setFixedHeight(220); self._lay.addWidget(g2)

        # Recent
        self._lay.addWidget(SectionHeader("Recently Added", len(items)))
        g3 = CardGrid(); g3.load(items[:12]); self._connect_grid(g3)
        self._lay.addWidget(g3)
        self._lay.addStretch()


class GenericView(QWidget):
    item_clicked = pyqtSignal(dict)
    item_edit = pyqtSignal(dict)
    item_delete = pyqtSignal(str)
    item_toggle = pyqtSignal(str)
    item_outlook = pyqtSignal(dict)

    def __init__(self, title, type_filter=None, parent=None):
        super().__init__(parent)
        self.title = title
        self.type_filter = type_filter
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        self.grid = CardGrid()
        self.grid.item_clicked.connect(self.item_clicked)
        self.grid.item_edit.connect(self.item_edit)
        self.grid.item_delete.connect(self.item_delete)
        self.grid.item_toggle.connect(self.item_toggle)
        self.grid.item_outlook.connect(self.item_outlook)
        lay.addWidget(self.grid)

    def refresh(self, search=None):
        if isinstance(self.type_filter, list):
            items = []
            for t in self.type_filter:
                items += db.get_items(type_filter=t, search=search)
            seen = set(); items = [x for x in items if not (x['id'] in seen or seen.add(x['id']))]
            items.sort(key=lambda x: x.get('created',''), reverse=True)
        else:
            items = db.get_items(type_filter=self.type_filter, search=search)
        self.grid.load(items)


class HealthView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        self._w = QWidget(); self._lay = QVBoxLayout(self._w)
        self._lay.setContentsMargins(0,0,6,20); self._lay.setSpacing(6)
        self.setWidget(self._w)

    def refresh(self):
        while self._lay.count():
            i = self._lay.takeAt(0)
            if i.widget(): i.widget().deleteLater()
        health = db.get_health()
        STATUS_COLOR = {'ok':'#3db87a','warn':'#d4812a','crit':'#e05252'}
        for status, label in [('crit','Critical'), ('warn','Degraded'), ('ok','Healthy')]:
            grp = [h for h in health if (h.get('s') or h.get('status','ok')) == status]
            if not grp: continue
            self._lay.addWidget(SectionHeader(label, len(grp)))
            hgrid = QGridLayout(); hgrid.setSpacing(6)
            for i, h in enumerate(grp):
                card = QFrame(); card.setObjectName("healthCard")
                cl = QHBoxLayout(card); cl.setContentsMargins(12,10,12,10)
                c = STATUS_COLOR.get(status,'#4a5470')
                dot = QLabel("●"); dot.setStyleSheet(f"color:{c};")
                name = QLabel(h.get('name','')); name.setObjectName("healthName")
                uptime = QLabel(h.get('uptime') or h.get('up','—'))
                uptime.setStyleSheet("font-size:10px;color:#4a5470;font-family:'Consolas';")
                lat = QLabel(h.get('latency') or h.get('lat','—'))
                lat.setStyleSheet("font-size:10px;color:#4a5470;font-family:'Consolas';")
                cycle_btn = QPushButton("⟳"); cycle_btn.setFixedSize(24,24)
                cycle_btn.setStyleSheet("background:#1f2432;border:1px solid #262d3d;border-radius:4px;color:#4a5470;")
                hid = h['id']
                def cycle(_, hid=hid):
                    h2 = next(x for x in db.get_health() if x['id']==hid)
                    nxt = {'ok':'warn','warn':'crit','crit':'ok'}.get(h2.get('s') or h2.get('status','ok'),'ok')
                    db.set_health_status(hid, nxt); self.refresh()
                cycle_btn.clicked.connect(cycle)
                cl.addWidget(dot); cl.addWidget(name,1); cl.addWidget(uptime); cl.addWidget(lat); cl.addWidget(cycle_btn)
                hgrid.addWidget(card, i//3, i%3)
            hw = QWidget(); hw.setLayout(hgrid)
            self._lay.addWidget(hw)
        self._lay.addStretch()


class OncallView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        self._w = QWidget(); self._lay = QVBoxLayout(self._w)
        self._lay.setContentsMargins(0,0,6,20)
        self.setWidget(self._w)

    def refresh(self):
        while self._lay.count():
            i = self._lay.takeAt(0)
            if i.widget(): i.widget().deleteLater()
        oncall = db.get_oncall()
        self._lay.addWidget(SectionHeader("On-Call Roster", len(oncall)))
        tbl = QTableWidget(len(oncall), 4)
        tbl.setHorizontalHeaderLabels(["Team","Name","Phone","Shift"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for r, oc in enumerate(oncall):
            for c, val in enumerate([oc.get('team',''), oc.get('name',''), oc.get('phone',''), oc.get('shift','')]):
                tbl.setItem(r, c, QTableWidgetItem(val))
        self._lay.addWidget(tbl)
        self._lay.addStretch()


class SLAView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        self._w = QWidget(); self._lay = QVBoxLayout(self._w)
        self._lay.setContentsMargins(0,0,6,20)
        self.setWidget(self._w)

    def refresh(self):
        while self._lay.count():
            i = self._lay.takeAt(0)
            if i.widget(): i.widget().deleteLater()
        sla_data = db.get_sla()
        self._lay.addWidget(SectionHeader("SLA Monitor"))
        for s in sla_data:
            ok = s['actual'] >= s['target']
            col = '#3db87a' if ok else ('#d4812a' if s['actual'] >= s['target']-1 else '#e05252')
            row = QWidget()
            rl = QHBoxLayout(row); rl.setContentsMargins(0,4,0,4)
            name = QLabel(s['name']); name.setFixedWidth(220)
            name.setStyleSheet("font-size:12px;color:#8892aa;")
            tgt = QLabel(f"tgt {s['target']}%"); tgt.setStyleSheet("font-size:10px;color:#4a5470;font-family:'Consolas';")
            tgt.setFixedWidth(60)
            bar = QProgressBar(); bar.setMaximum(10000); bar.setValue(int(s['actual']*100))
            bar.setTextVisible(False); bar.setFixedHeight(5)
            bar.setStyleSheet(f"QProgressBar::chunk{{background:{col};}}")
            pct = QLabel(f"{s['actual']}%"); pct.setStyleSheet(f"font-size:12px;font-family:'Consolas';font-weight:500;color:{col};")
            pct.setFixedWidth(50); pct.setAlignment(Qt.AlignmentFlag.AlignRight)
            status = QLabel("OK" if ok else "BREACH")
            status.setStyleSheet(f"font-size:9px;padding:2px 6px;border-radius:2px;background:rgba(0,0,0,.3);color:{col};font-family:'Consolas';")
            rl.addWidget(name); rl.addWidget(tgt); rl.addWidget(bar,1); rl.addWidget(pct); rl.addWidget(status)
            self._lay.addWidget(row)
        self._lay.addStretch()


class AnalyticsView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        self._w = QWidget(); self._lay = QVBoxLayout(self._w)
        self._lay.setContentsMargins(0,0,6,20)
        self.setWidget(self._w)

    def refresh(self):
        while self._lay.count():
            i = self._lay.takeAt(0)
            if i.widget(): i.widget().deleteLater()
        items = db.get_items()
        today = datetime.now().strftime('%Y-%m-%d')
        today_cnt = sum(1 for i in items if i.get('date','')[:10] == today)
        inc = [i for i in items if i['type'] == 'incident']

        # Stats
        stat_row = QHBoxLayout()
        for num, lbl, col in [
            (len(items),"Total Items","#7aaef5"),
            (today_cnt,"Added Today","#4ed4c4"),
            (sum(1 for i in items if i.get('date','')[:10] >= datetime.now().strftime('%Y-%m-01')),"This Month","#a584e0"),
            (sum(1 for i in items if i['type']=='todo' and not i['done']),"Open Todos","#f0a84a"),
            (len(inc),"Incidents","#ff7070"),
            (sum(1 for s in db.get_sla() if s['actual']<s['target']),"SLA Breaches","#e05252"),
        ]:
            stat_row.addWidget(StatBox(num, lbl, col))
        self._lay.addLayout(stat_row)

        # Type breakdown
        self._lay.addWidget(SectionHeader("Items by Type"))
        type_counts = {}
        for it in items: type_counts[it['type']] = type_counts.get(it['type'],0)+1
        max_count = max(type_counts.values(),default=1)
        for t, cnt in sorted(type_counts.items(), key=lambda x:-x[1]):
            row = QWidget(); rl = QHBoxLayout(row); rl.setContentsMargins(0,3,0,3)
            lbl = QLabel(f"{TYPE_EMOJI.get(t,'✦')} {t.upper()}")
            lbl.setStyleSheet("font-size:11px;color:#8892aa;font-family:'Consolas';"); lbl.setFixedWidth(130)
            bar = QProgressBar(); bar.setMaximum(max_count); bar.setValue(cnt)
            bar.setTextVisible(False); bar.setFixedHeight(5)
            col = TYPE_COLOR.get(t,'#4a5470')
            bar.setStyleSheet(f"QProgressBar::chunk{{background:{col};}}")
            num_lbl = QLabel(str(cnt)); num_lbl.setStyleSheet("font-size:11px;color:#4a5470;font-family:'Consolas';"); num_lbl.setFixedWidth(25)
            rl.addWidget(lbl); rl.addWidget(bar,1); rl.addWidget(num_lbl)
            self._lay.addWidget(row)
        self._lay.addStretch()


# ── MAIN WINDOW ───────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpsVault — Banking Ops Command Center")
        self.setMinimumSize(1200, 720)
        self.current_item = None
        self._build_ui()
        self._setup_shortcuts()
        self._setup_reminder_timer()
        self.nav_home()

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ── TOPNAV ──
        topbar = QWidget(); topbar.setObjectName("topbar"); topbar.setFixedHeight(52)
        tl = QHBoxLayout(topbar); tl.setContentsMargins(0,0,12,0); tl.setSpacing(0)

        brand = QWidget(); brand.setFixedWidth(220)
        brand.setStyleSheet("background:#111318;border-right:1px solid #1a1e2a;")
        bl = QHBoxLayout(brand); bl.setContentsMargins(16,0,16,0); bl.setSpacing(10)
        logo = QLabel("⬡"); logo.setStyleSheet("font-size:20px;color:#c8a84b;")
        bname = QLabel("OpsVault"); bname.setStyleSheet("font-size:15px;font-weight:500;color:#dde1eb;")
        bl.addWidget(logo); bl.addWidget(bname); bl.addStretch()
        tl.addWidget(brand)

        # Search
        tl.addSpacing(16)
        self.search_box = QLineEdit(); self.search_box.setObjectName("searchBox")
        self.search_box.setPlaceholderText("⌕  Search incidents, queries, runbooks, tickets… (/ to focus)")
        self.search_box.setFixedWidth(460); self.search_box.setFixedHeight(34)
        self.search_box.textChanged.connect(self._on_search)
        tl.addWidget(self.search_box)
        tl.addStretch()

        # Nav pills
        for text, fn in [("Incidents", self.nav_incidents), ("On-Call", self.nav_oncall),
                         ("SLA", self.nav_sla), ("📅 Outlook Export", self.export_all_outlook)]:
            btn = QPushButton(text); btn.clicked.connect(fn)
            tl.addWidget(btn)

        # Env switcher
        tl.addSpacing(8)
        self.env_combo = QComboBox(); self.env_combo.addItems(["PROD","UAT","DEV"])
        self.env_combo.setFixedWidth(80)
        self.env_combo.setStyleSheet("background:#1f2432;border:1px solid #262d3d;border-radius:5px;padding:4px 8px;color:#dde1eb;font-family:'Consolas';font-size:11px;")
        tl.addWidget(self.env_combo)
        tl.addSpacing(8)

        add_btn = QPushButton("+ Add"); add_btn.setObjectName("addBtn")
        add_btn.setFixedHeight(34); add_btn.clicked.connect(self.open_add)
        tl.addWidget(add_btn)
        root.addWidget(topbar)

        # ── INCIDENT BANNER ──
        self.inc_banner = QWidget(); self.inc_banner.setObjectName("incBanner")
        self.inc_banner.setFixedHeight(34); self.inc_banner.hide()
        ibl = QHBoxLayout(self.inc_banner); ibl.setContentsMargins(20,0,20,0)
        self.inc_banner_lbl = QLabel(); self.inc_banner_lbl.setObjectName("incBannerText")
        view_inc = QPushButton("View →"); view_inc.setFixedHeight(22)
        view_inc.setStyleSheet("background:transparent;border:1px solid #5a1010;color:#ff7070;border-radius:3px;padding:0 8px;font-size:10px;")
        view_inc.clicked.connect(self.nav_incidents)
        ibl.addWidget(QLabel("🔴")); ibl.addWidget(self.inc_banner_lbl,1); ibl.addWidget(view_inc)
        root.addWidget(self.inc_banner)

        # ── CAPTURE BAR ──
        capbar = QWidget(); capbar.setObjectName("capBar"); capbar.setFixedHeight(50)
        cl = QHBoxLayout(capbar); cl.setContentsMargins(16,8,16,8); cl.setSpacing(8)
        arrow = QLabel("›"); arrow.setStyleSheet("color:#4a5470;font-size:16px;")
        self.cap_input = QLineEdit(); self.cap_input.setObjectName("capInput")
        self.cap_input.setPlaceholderText("Paste URL · INC0001 · TCI-123 · note · todo · Splunk query… Enter to save")
        self.cap_input.returnPressed.connect(self.cap_submit)
        self.cap_input.textChanged.connect(self._cap_detect)
        self.cap_type_lbl = QLabel("auto"); self.cap_type_lbl.setObjectName("capTypeLabel")
        save_btn = QPushButton("↵ Save"); save_btn.setObjectName("btnPrimary")
        save_btn.setFixedHeight(32); save_btn.clicked.connect(self.cap_submit)
        cl.addWidget(arrow); cl.addWidget(self.cap_input,1); cl.addWidget(self.cap_type_lbl); cl.addWidget(save_btn)
        root.addWidget(capbar)

        # ── BODY ──
        body_row = QHBoxLayout(); body_row.setContentsMargins(0,0,0,0); body_row.setSpacing(0)

        # Sidebar
        sidebar = QWidget(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(220)
        sl = QVBoxLayout(sidebar); sl.setContentsMargins(0,8,0,0); sl.setSpacing(0)
        self.nav_buttons = {}

        def nav_btn(text, fn, id):
            b = QPushButton(text); b.setProperty("active","false")
            b.clicked.connect(fn); b.clicked.connect(lambda: self._set_active(id))
            sl.addWidget(b); self.nav_buttons[id] = b; return b

        for lbl in ["WORKSPACE"]:
            l = QLabel(lbl); l.setObjectName("sidebarSection"); sl.addWidget(l)
        nav_btn("⌂  Home", self.nav_home, "home")
        nav_btn("◫  Timeline", self.nav_timeline, "timeline")
        nav_btn("▦  Calendar", self.nav_calendar, "calendar")
        nav_btn("◈  Analytics", self.nav_analytics, "analytics")

        sl.addWidget(self._sep_label("OPERATIONS"))
        self.inc_cnt_btn = nav_btn("🚨  Incidents", self.nav_incidents, "incidents")
        nav_btn("♥  System Health", self.nav_health, "health")
        nav_btn("🔄  Change Mgmt", self.nav_changes, "changes")
        nav_btn("📱  On-Call Roster", self.nav_oncall, "oncall")
        nav_btn("📈  SLA Monitor", self.nav_sla, "sla")

        sl.addWidget(self._sep_label("KNOWLEDGE"))
        nav_btn("📋  Runbooks", self.nav_runbooks, "runbooks")
        nav_btn("🔍  Query Library", self.nav_queries, "queries")
        nav_btn("👤  Contacts", self.nav_contacts, "contacts")
        nav_btn("🛡️  Compliance", self.nav_compliance, "compliance")

        sl.addWidget(self._sep_label("PERSONAL"))
        self.todo_cnt_btn = nav_btn("☐  My Todos", self.nav_todos, "todos")
        nav_btn("📝  My Notes", self.nav_notes, "notes")
        nav_btn("🔗  Link Vault", self.nav_links, "links")

        sl.addStretch()
        body_row.addWidget(sidebar)

        # Content stack
        self.stack = QStackedWidget()
        self.view_home = HomeView()
        self.view_timeline = GenericView("Timeline")
        self.view_calendar = self._make_calendar()
        self.view_analytics = AnalyticsView()
        self.view_incidents = GenericView("Incidents", ["incident","alert","snow"])
        self.view_health = HealthView()
        self.view_changes = GenericView("Changes", ["change","tci"])
        self.view_oncall = OncallView()
        self.view_sla = SLAView()
        self.view_runbooks = GenericView("Runbooks", "runbook")
        self.view_queries = GenericView("Queries", ["splunk","jira","grafana"])
        self.view_contacts = GenericView("Contacts", "contact")
        self.view_compliance = GenericView("Compliance", "compliance")
        self.view_todos = GenericView("Todos", "todo")
        self.view_notes = GenericView("Notes", "note")
        self.view_links = GenericView("Links", "link")

        self._all_generic = [self.view_timeline, self.view_incidents, self.view_changes,
            self.view_runbooks, self.view_queries, self.view_contacts,
            self.view_compliance, self.view_todos, self.view_notes, self.view_links]
        for v in self._all_generic:
            v.item_clicked.connect(self._open_detail)
            v.item_edit.connect(self.open_edit)
            v.item_delete.connect(self._delete_item)
            v.item_toggle.connect(self._toggle_done)
            v.item_outlook.connect(self._export_single_outlook)
        self.view_home.item_clicked.connect(self._open_detail)
        self.view_home.item_edit.connect(self.open_edit)
        self.view_home.item_delete.connect(self._delete_item)
        self.view_home.item_toggle.connect(self._toggle_done)
        self.view_home.item_outlook.connect(self._export_single_outlook)

        for v in [self.view_home, self.view_timeline, self.view_calendar, self.view_analytics,
                  self.view_incidents, self.view_health, self.view_changes, self.view_oncall,
                  self.view_sla, self.view_runbooks, self.view_queries, self.view_contacts,
                  self.view_compliance, self.view_todos, self.view_notes, self.view_links]:
            self.stack.addWidget(v)

        body_row.addWidget(self.stack, 1)

        # Detail panel
        self.detail = DetailPanel()
        self.detail.hide()
        self.detail.closed.connect(lambda: self.detail.hide())
        self.detail.edit_requested.connect(self.open_edit)
        self.detail.delete_requested.connect(self._delete_item)
        self.detail.toggle_done.connect(self._toggle_done)
        self.detail.outlook_export.connect(self._export_single_outlook)
        body_row.addWidget(self.detail)

        bw = QWidget(); bw.setLayout(body_row)
        root.addWidget(bw, 1)

    def _sep_label(self, text):
        l = QLabel(text); l.setObjectName("sidebarSection")
        l.setStyleSheet("color:#2e3550;font-size:9px;font-weight:bold;letter-spacing:1px;padding:12px 14px 4px;")
        return l

    def _make_calendar(self):
        w = QWidget(); l = QVBoxLayout(w)
        lbl = QLabel("📅 Calendar — open Timeline view and filter by date.\nFull calendar widget coming in next update.")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color:#4a5470;font-size:14px;padding:60px;")
        l.addWidget(lbl)
        return w

    def _set_active(self, id):
        for bid, btn in self.nav_buttons.items():
            btn.setProperty("active", "true" if bid==id else "false")
            btn.style().unpolish(btn); btn.style().polish(btn)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("N"), self, self.open_add)
        QShortcut(QKeySequence("/"), self, lambda: self.search_box.setFocus())
        QShortcut(QKeySequence("Ctrl+N"), self, self.open_add)
        QShortcut(QKeySequence("Escape"), self, lambda: self.detail.hide())

    def _setup_reminder_timer(self):
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self._check_reminders)
        self.reminder_timer.start(60000)
        self._check_reminders()

    def _check_reminders(self):
        items = db.get_items()
        now = datetime.now()
        inc = [i for i in items if i['type'] in ('incident','alert')]
        overdue = [i for i in items if i.get('due') and not i.get('done')]
        overdue = [i for i in overdue if datetime.fromisoformat(i['due']) < now]

        if inc:
            p1 = [i for i in inc if 'P1' in (i.get('priority',''))]
            text = f"🚨 {len(p1)} P1 active: " + " · ".join(i['title'][:40] for i in p1[:2]) if p1 else f"{len(inc)} active incidents"
            self.inc_banner_lbl.setText(text)
            self.inc_banner.show()
        elif overdue:
            self.inc_banner_lbl.setText(f"⏰ {len(overdue)} overdue item(s): " + ", ".join(i['title'][:30] for i in overdue[:2]))
            self.inc_banner.show()
        else:
            self.inc_banner.hide()

        # Due soon: show message box for items due within remind window
        for item in items:
            if not item.get('due') or item.get('done'): continue
            try:
                due = datetime.fromisoformat(item['due'])
                remind = int(item.get('remind') or 15)
                mins_until = (due - now).total_seconds() / 60
                if 0 < mins_until <= remind:
                    QMessageBox.information(self, "OpsVault Reminder",
                        f"⏰ Due in {int(mins_until)} minutes:\n\n{item['title']}\n\nPriority: {item.get('priority','—')}")
            except: pass

        self._update_badges(items)

    def _update_badges(self, items=None):
        if items is None: items = db.get_items()
        open_inc = sum(1 for i in items if i['type'] in ('incident','alert'))
        open_todo = sum(1 for i in items if i['type']=='todo' and not i['done'])
        self.inc_cnt_btn.setText(f"🚨  Incidents  [{open_inc}]" if open_inc else "🚨  Incidents")
        self.todo_cnt_btn.setText(f"☐  My Todos  [{open_todo}]" if open_todo else "☐  My Todos")

    # ── NAV ──
    def _show(self, widget, refresh_fn):
        self.stack.setCurrentWidget(widget); refresh_fn()
    def nav_home(self): self._show(self.view_home, self.view_home.refresh); self._set_active("home")
    def nav_timeline(self): self._show(self.view_timeline, lambda: self.view_timeline.refresh()); self._set_active("timeline")
    def nav_calendar(self): self.stack.setCurrentWidget(self.view_calendar); self._set_active("calendar")
    def nav_analytics(self): self._show(self.view_analytics, self.view_analytics.refresh); self._set_active("analytics")
    def nav_incidents(self): self._show(self.view_incidents, lambda: self.view_incidents.refresh()); self._set_active("incidents")
    def nav_health(self): self._show(self.view_health, self.view_health.refresh); self._set_active("health")
    def nav_changes(self): self._show(self.view_changes, lambda: self.view_changes.refresh()); self._set_active("changes")
    def nav_oncall(self): self._show(self.view_oncall, self.view_oncall.refresh); self._set_active("oncall")
    def nav_sla(self): self._show(self.view_sla, self.view_sla.refresh); self._set_active("sla")
    def nav_runbooks(self): self._show(self.view_runbooks, lambda: self.view_runbooks.refresh()); self._set_active("runbooks")
    def nav_queries(self): self._show(self.view_queries, lambda: self.view_queries.refresh()); self._set_active("queries")
    def nav_contacts(self): self._show(self.view_contacts, lambda: self.view_contacts.refresh()); self._set_active("contacts")
    def nav_compliance(self): self._show(self.view_compliance, lambda: self.view_compliance.refresh()); self._set_active("compliance")
    def nav_todos(self): self._show(self.view_todos, lambda: self.view_todos.refresh()); self._set_active("todos")
    def nav_notes(self): self._show(self.view_notes, lambda: self.view_notes.refresh()); self._set_active("notes")
    def nav_links(self): self._show(self.view_links, lambda: self.view_links.refresh()); self._set_active("links")

    # ── ACTIONS ──
    def _open_detail(self, item):
        self.current_item = item; self.detail.load(item); self.detail.show()

    def open_add(self, prefill=None):
        dlg = dialogs.ItemDialog(self, db.get_folders(), prefill)
        if dlg.exec():
            data = dlg.get_data()
            if not data['title']: return
            db.save_item(data); self._refresh_current(); self._update_badges()

    def open_edit(self, item):
        dlg = dialogs.ItemDialog(self, db.get_folders(), item)
        if dlg.exec():
            data = dlg.get_data()
            db.save_item(data)
            if self.detail.isVisible(): self.detail.load(db.get_item(item['id']))
            self._refresh_current(); self._update_badges()

    def _delete_item(self, id):
        if QMessageBox.question(self, "Delete", "Delete this item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            db.delete_item(id); self.detail.hide(); self._refresh_current(); self._update_badges()

    def _toggle_done(self, id):
        db.toggle_done(id)
        if self.detail.isVisible():
            updated = db.get_item(id)
            if updated: self.detail.load(updated)
        self._refresh_current(); self._update_badges()

    def _export_single_outlook(self, item):
        if not item.get('due') and not item.get('date'):
            QMessageBox.warning(self, "No Date", "Set a due date on this item first."); return
        path = ics_export.export_ics([item])
        ics_export.open_in_outlook(path)
        QMessageBox.information(self, "Outlook", f"📅 Calendar entry created!\n\nDouble-click the .ics file to open in Outlook:\n{path}")

    def export_all_outlook(self):
        items = db.get_items()
        exportable = [i for i in items if i.get('due') or i['type'] in ('change','tci','incident','todo')]
        if not exportable:
            QMessageBox.information(self, "Nothing to export", "No items with dates found."); return
        path, _ = QFileDialog.getSaveFileName(self, "Save Calendar Export", 
            os.path.expanduser("~/opsvault-export.ics"), "ICS Files (*.ics)")
        if not path: return
        ics_export.export_ics(exportable, path)
        ics_export.open_in_outlook(path)
        QMessageBox.information(self, "Exported", f"📅 {len(exportable)} items exported to Outlook!\n{path}")

    def _on_search(self, text):
        cur = self.stack.currentWidget()
        if hasattr(cur, 'refresh') and cur in self._all_generic:
            cur.refresh(search=text if text else None)

    def _cap_detect(self, text):
        t = text.strip()
        detected = "auto"
        if t.startswith('http'):
            if 'splunk' in t: detected='splunk'
            elif 'jira' in t or 'atlassian' in t: detected='jira'
            elif 'servicenow' in t or 'snow.' in t: detected='snow'
            elif 'grafana' in t: detected='grafana'
            else: detected='link'
        elif t.upper().startswith(('INC','CHG','RITM')): detected='snow'
        elif t.upper().startswith('TCI-'): detected='tci'
        elif 'index=' in t or '| stats' in t: detected='splunk'
        self.cap_type_lbl.setText(detected)

    def cap_submit(self):
        import uuid
        text = self.cap_input.text().strip()
        if not text: return
        detected_type = self.cap_type_lbl.text()
        if detected_type == 'auto': detected_type = 'note'
        url = text if text.startswith('http') else ''
        title = text
        if url:
            try:
                from urllib.parse import urlparse
                p = urlparse(url); title = p.netloc.replace('www.','') + p.path[:50]
            except: title = url[:80]
        item = {
            'id': str(uuid.uuid4()), 'type': detected_type, 'title': title,
            'body': '' if url else text, 'url': url, 'folder': db.get_folders()[0]['id'] if db.get_folders() else '',
            'env': self.env_combo.currentText(), 'priority': '', 'tags': '[]',
            'date': datetime.now().strftime('%Y-%m-%d'), 'due': '', 'remind': 15, 'done': 0,
            'created': datetime.now().isoformat(),
        }
        db.save_item(item)
        self.cap_input.clear(); self.cap_type_lbl.setText("auto")
        self._refresh_current(); self._update_badges()
        self.statusBar().showMessage(f"✦ Saved as {detected_type}", 3000)

    def _refresh_current(self):
        cur = self.stack.currentWidget()
        if hasattr(cur, 'refresh'): cur.refresh()


def main():
    db.init_db()
    app = QApplication(sys.argv)
    app.setApplicationName("OpsVault")
    app.setStyleSheet(styles.DARK)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
