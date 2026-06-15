DARK = """
QWidget { background:#0d1017; color:#dde1eb; font-family:'Segoe UI'; font-size:13px; }
QMainWindow { background:#0d1017; }
QSplitter::handle { background:#1a1e2a; width:1px; }

/* Sidebar */
#sidebar { background:#111318; border-right:1px solid #1a1e2a; }
#sidebar QPushButton {
    background:transparent; border:none; border-left:2px solid transparent;
    color:#4a5470; text-align:left; padding:7px 10px 7px 16px;
    font-size:12px; border-radius:0;
}
#sidebar QPushButton:hover { background:#1a1e2a; color:#8892aa; }
#sidebar QPushButton[active="true"] { background:#1f2432; color:#dde1eb; border-left:2px solid #c8a84b; }
#sidebar QLabel { color:#2e3550; font-size:9px; font-weight:bold; letter-spacing:1px; padding:12px 14px 4px; }

/* Topbar */
#topbar { background:#111318; border-bottom:1px solid #1a1e2a; }
#topbar QPushButton {
    background:transparent; border:1px solid transparent;
    color:#8892aa; padding:5px 12px; border-radius:6px; font-size:12px;
}
#topbar QPushButton:hover { background:#1a1e2a; border-color:#1f2432; color:#dde1eb; }
#topbar QPushButton#addBtn {
    background:#c8a84b; color:#0d1017; font-weight:bold; border-color:#c8a84b;
}
#topbar QPushButton#addBtn:hover { background:#e2c97e; }

/* Search */
#searchBox {
    background:#0d1017; border:1px solid #1f2432; border-radius:7px;
    padding:7px 12px; color:#dde1eb; font-family:'Consolas'; font-size:12px;
}
#searchBox:focus { border-color:#c8a84b; }

/* Capture bar */
#capBar { background:#111318; border-bottom:1px solid #1a1e2a; }
#capInput {
    background:#0d1017; border:1px solid #1f2432; border-radius:7px;
    padding:8px 12px; color:#dde1eb; font-family:'Consolas'; font-size:12px;
}
#capInput:focus { border-color:#c8a84b; }
#capTypeLabel {
    background:#1f2432; border:1px solid #262d3d; border-radius:3px;
    color:#4a5470; padding:3px 8px; font-family:'Consolas'; font-size:10px;
}

/* Cards */
#cardWidget {
    background:#111318; border:1px solid #1a1e2a; border-radius:10px;
    padding:13px 15px;
}
#cardWidget:hover { background:#181c26; border-color:#1f2432; }
#typeLabel { font-family:'Consolas'; font-size:9px; font-weight:bold; letter-spacing:1px; }
#cardTitle { font-size:13px; font-weight:500; color:#dde1eb; }
#cardBody { font-size:11px; color:#8892aa; font-family:'Consolas'; }
#cardUrl { font-size:10px; color:#7aaef5; font-family:'Consolas'; }
#cardMeta { font-size:10px; color:#4a5470; font-family:'Consolas'; }
#tag { background:#1f2432; color:#4a5470; font-family:'Consolas'; font-size:9px; padding:2px 6px; border-radius:2px; }
#overdueTag { background:#2a0f0f; color:#ff7070; font-family:'Consolas'; font-size:9px; padding:2px 6px; border-radius:2px; }
#dueTag { background:#1e1608; color:#f0a84a; font-family:'Consolas'; font-size:9px; padding:2px 6px; border-radius:2px; }

/* Stat boxes */
#statBox { background:#111318; border:1px solid #1a1e2a; border-radius:10px; padding:14px 16px; }
#statNum { font-size:22px; font-weight:500; font-family:'Consolas'; }
#statLabel { font-size:10px; color:#4a5470; letter-spacing:.4px; }

/* Health */
#healthCard { background:#111318; border:1px solid #1a1e2a; border-radius:8px; padding:10px 13px; }
#healthCard:hover { border-color:#1f2432; }
#healthName { font-size:12px; color:#8892aa; }
#healthVal { font-size:10px; color:#4a5470; font-family:'Consolas'; }

/* Tables */
QTableWidget {
    background:#0d1017; border:1px solid #1a1e2a; border-radius:8px;
    gridline-color:#1a1e2a; color:#8892aa; font-size:12px;
}
QTableWidget::item:hover { background:#111318; }
QTableWidget::item:selected { background:#1f2432; color:#dde1eb; }
QHeaderView::section {
    background:#111318; color:#4a5470; border:none; border-bottom:1px solid #1a1e2a;
    padding:5px 10px; font-size:9px; font-family:'Consolas'; letter-spacing:.8px;
    text-transform:uppercase;
}

/* Buttons */
QPushButton#btnPrimary {
    background:#c8a84b; color:#0d1017; border:none; padding:7px 16px;
    border-radius:6px; font-weight:bold; font-size:12px;
}
QPushButton#btnPrimary:hover { background:#e2c97e; }
QPushButton#btnSecondary {
    background:transparent; color:#8892aa; border:1px solid #1f2432;
    padding:7px 16px; border-radius:6px; font-size:12px;
}
QPushButton#btnSecondary:hover { background:#1a1e2a; color:#dde1eb; }
QPushButton#btnDanger:hover { border-color:#e05252; color:#e05252; }
QPushButton#btnOutlook {
    background:#0f1e3a; color:#7aaef5; border:1px solid #1f3a6a;
    padding:7px 16px; border-radius:6px; font-size:12px;
}
QPushButton#btnOutlook:hover { background:#1a2e50; }

/* Dialog / Form */
QDialog { background:#111318; border:1px solid #1f2432; border-radius:12px; }
QLineEdit, QTextEdit, QDateTimeEdit, QComboBox, QSpinBox {
    background:#0d1017; border:1px solid #262d3d; border-radius:6px;
    padding:7px 10px; color:#dde1eb; font-family:'Consolas'; font-size:12px;
}
QLineEdit:focus, QTextEdit:focus, QDateTimeEdit:focus, QComboBox:focus {
    border-color:#c8a84b;
}
QComboBox::drop-down { border:none; }
QComboBox QAbstractItemView { background:#1a1e2a; border:1px solid #262d3d; color:#dde1eb; selection-background-color:#1f2432; }
QLabel#fieldLabel { font-size:9px; color:#4a5470; letter-spacing:.6px; font-family:'Consolas'; }
QLabel#sectionLabel { font-size:10px; color:#2e3550; font-weight:bold; letter-spacing:1px; font-family:'Consolas'; }

/* Scrollbars */
QScrollBar:vertical { background:#0d1017; width:4px; }
QScrollBar::handle:vertical { background:#1f2432; border-radius:2px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { background:#0d1017; height:4px; }
QScrollBar::handle:horizontal { background:#1f2432; border-radius:2px; }

/* Tabs */
QTabWidget::pane { border:none; background:#0d1017; }
QTabBar::tab { background:#111318; color:#4a5470; padding:8px 18px; border:none; font-size:12px; }
QTabBar::tab:selected { color:#dde1eb; border-bottom:2px solid #c8a84b; background:#0d1017; }
QTabBar::tab:hover { color:#8892aa; }

/* SLA / progress */
QProgressBar { background:#1f2432; border:none; border-radius:3px; height:5px; }
QProgressBar::chunk { border-radius:3px; }

/* Incident banner */
#incBanner { background:#1a0808; border-bottom:1px solid #3a1010; }
#incBannerText { color:#ff7070; font-family:'Consolas'; font-size:11px; }
"""
