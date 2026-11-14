import sys, os, re, json, random, zipfile, tempfile, shutil
from pathlib import Path
from PyQt6.QtCore import Qt, QUrl, QTimer, QSettings, QEvent, QSize, QRect, QRectF
from PyQt6.QtGui import QIcon, QShortcut, QKeySequence, QCursor, QPixmap, QColor, QFont, QPainter, QPainterPath, QFontMetrics, QPalette
from PyQt6.QtWidgets import *
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
import threading, subprocess, urllib.request, urllib.error, time
from PyQt6.QtCore import pyqtSignal
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings
except Exception:
    QWebEngineView = None

__version__ = "1.0.0"                      # keep in sync with installer.iss
UPDATE_REPO = ""                           # your GitHub "owner/repo" that hosts releases
YT_PLAYLIST = "PLzdPgQvHT2bpN6XE_i_SnTErvBtKycHwg"

EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".mp3", ".m4a", ".wav", ".ogg", ".opus"}
SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
STYLE = """
QWidget{background:@@bg@@;color:@@text@@;font-family:'@@font@@','Segoe UI',Arial,sans-serif;font-size:@@size@@px}
QLabel{background:transparent}
QSplitter::handle{background:@@bg@@}
QLabel#brand{font-size:19px;font-weight:700}
QLineEdit#search{background:@@bg@@;border:1px solid @@border@@;border-right:none;border-top-left-radius:20px;border-bottom-left-radius:20px;border-top-right-radius:0;border-bottom-right-radius:0;padding:8px 18px;font-size:14px;min-height:20px}
QLineEdit#search:focus{border:1px solid #1c62b9;border-right:none}
QPushButton#searchbtn{background:@@surface@@;border:1px solid @@border@@;border-top-left-radius:0;border-bottom-left-radius:0;border-top-right-radius:20px;border-bottom-right-radius:20px;padding:8px 22px;min-height:20px}
QPushButton#searchbtn:hover{background:@@hover@@}
QPushButton#icon{background:transparent;border-radius:18px;min-width:36px;max-width:36px;min-height:36px;max-height:36px;font-size:16px;padding:0}
QPushButton#icon:hover{background:@@surface@@}
QPushButton#pill{background:@@surface@@;border-radius:16px;padding:7px 14px;font-weight:600;color:@@text@@}
QPushButton#pill:hover{background:@@hover@@}
QPushButton#pill:checked{background:@@text@@;color:@@bg@@}
QWidget#side{background:@@bg@@;border:1px solid @@border@@;border-radius:12px}
QLabel#head{font-size:18px;font-weight:700;padding:2px 2px 0 2px}
QLabel#nowTitle{font-size:20px;font-weight:700}
QLabel#author{font-size:15px;font-weight:600}
QLabel#avatar{background:@@accent@@;color:@@onacc@@;border-radius:18px;min-width:36px;max-width:36px;min-height:36px;max-height:36px;font-weight:700;font-size:15px;qproperty-alignment:AlignCenter}
QLabel#desc{background:@@surface@@;border-radius:12px;padding:12px 14px;font-weight:600}
QLabel#nowMeta{color:@@muted@@;font-size:12px}
QListWidget{background:transparent;border:none;outline:0}
QLineEdit{background:@@surface@@;border:1px solid @@border@@;border-radius:@@r@@px;padding:7px 10px}
QLineEdit:focus{border-color:@@accent@@}
QComboBox{background:@@surface@@;border:1px solid @@border@@;border-radius:@@r@@px;padding:5px 8px}
QComboBox QAbstractItemView{background:@@surface@@;selection-background-color:@@hover@@}
QPushButton{background:transparent;border:none;border-radius:@@r@@px;padding:7px 10px;color:@@btntext@@}
QPushButton:hover{background:@@surface@@}
QPushButton:checked{background:@@tint@@;color:@@acchover@@}
QSlider::groove:horizontal{height:3px;background:@@groove@@;border-radius:1px}
QSlider::sub-page:horizontal{background:@@accent@@;border-radius:1px}
QSlider::handle:horizontal{background:@@accent@@;width:13px;height:13px;margin:-5px 0;border-radius:6px}
QScrollBar:vertical{background:transparent;width:10px;margin:2px}
QScrollBar::handle:vertical{background:@@groove@@;border-radius:4px;min-height:30px}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
QPushButton#play{background:@@text@@;color:@@bg@@;border-radius:17px;min-width:34px;max-width:34px;min-height:34px;max-height:34px;font-size:14px;padding:0}
QPushButton#play:hover{background:@@itemtext@@}
QPushButton#primary{background:@@accent@@;color:@@onacc@@;padding:8px 24px;font-weight:600;border-radius:18px}
QPushButton#primary:hover{background:@@acchover@@}
QPushButton::menu-indicator{image:none;width:0}
QMenu{background:@@surface@@;border:1px solid @@border@@;border-radius:12px;padding:8px}
QMenu::item{padding:8px 24px;border-radius:8px}
QMenu::item:selected{background:@@hover@@}
QDialog{background:@@bg@@}
QToolTip{background:@@surface@@;color:@@text@@;border:1px solid @@groove@@;padding:4px 8px}
"""

DEFAULTS = dict(preset="YouTube Dark", bg="#0f0f0f", text="#f1f1f1", accent="#ff0000", font="Segoe UI", size=13, radius=8,
                side="right", thumbs=True, step=5, resume=True, mini_opacity=100)
PRESETS = {"YouTube Dark": dict(bg="#0f0f0f", text="#f1f1f1", accent="#ff0000"), "YouTube Light": dict(bg="#ffffff", text="#0f0f0f", accent="#ff0000"), "Midnight red": dict(bg="#0f0f11", text="#e9e9ec", accent="#ff4b3e"), "Ocean": dict(bg="#0b1220", text="#e6edf7", accent="#3b9cff"),
           "Forest": dict(bg="#0e1411", text="#e4efe8", accent="#3ecf8e"), "Violet": dict(bg="#120f1a", text="#ece8f5", accent="#a678ff"),
           "Sunset": dict(bg="#16100e", text="#f3e9e4", accent="#ff9140"), "Mono": dict(bg="#101010", text="#eeeeee", accent="#d8d8d8"),
           "Light": dict(bg="#f4f4f6", text="#18181b", accent="#e5392c")}
OPT = dict(DEFAULTS); PAL = {}
def mix(a, b, t):
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t), round(ca.green() + (cb.green() - ca.green()) * t), round(ca.blue() + (cb.blue() - ca.blue()) * t)).name()
def themed(css):
    bg, tx, ac = OPT["bg"], OPT["text"], OPT["accent"]; dark = QColor(bg).lightnessF() < .5
    d = {"bg": bg, "panel": mix(bg, tx, .035), "surface": mix(bg, tx, .10 if dark else .05), "hover": mix(bg, tx, .17 if dark else .10), "border": mix(bg, tx, .15 if dark else .12), "groove": mix(bg, tx, .24 if dark else .18),
         "tint": mix(bg, ac, .22), "accent": ac, "acchover": mix(ac, "#ffffff", .2), "acctext": mix(ac, "#ffffff" if dark else "#000000", .25), "text": tx,
         "itemtext": mix(tx, bg, .18), "btntext": mix(tx, bg, .08), "muted": mix(tx, bg, .33), "onacc": "#ffffff" if QColor(ac).lightnessF() < .6 else "#111111",
         "font": OPT["font"], "size": str(OPT["size"]), "r": str(OPT["radius"])}
    PAL.update(d)
    for k, v in d.items(): css = css.replace(f"@@{k}@@", v)
    return css

def _excepthook(t, e, tb):
    import traceback
    msg = "".join(traceback.format_exception(t, e, tb))
    try:
        d = Path.home() / ".playlistplayer"; d.mkdir(exist_ok=True)
        with open(d / "error.log", "a", encoding="utf-8") as f: f.write(msg + "\n")
    except Exception: pass
    try: QMessageBox.critical(None, "Something went wrong", f"{e}\n\nDetails were saved to  {Path.home() / '.playlistplayer' / 'error.log'}")
    except Exception: pass

ROLE_TITLE, ROLE_SUB, ROLE_THUMB, ROLE_PROG, ROLE_DUR, ROLE_DONE, ROLE_NUM = [Qt.ItemDataRole.UserRole + i for i in range(1, 8)]
def wrap2(fm, text, w):
    words, lines, cur = text.split(), [], ""
    while words:
        t = (cur + " " + words[0]).strip()
        if fm.horizontalAdvance(t) <= w or not cur: cur = t; words.pop(0)
        else:
            lines.append(cur); cur = ""
            if len(lines) == 2: break
    if len(lines) < 2 and cur: lines.append(cur); cur = ""
    rest = " ".join(([cur] if cur else []) + words)
    if rest and lines: lines[-1] = fm.elidedText(lines[-1] + " " + rest, Qt.TextElideMode.ElideRight, w)
    return lines or [""]

class VideoDelegate(QStyledItemDelegate):
    """YouTube-style row: number, rounded thumbnail with duration + red progress bar, bold title, grey details."""
    TW, TH = 120, 68
    def sizeHint(self, opt, idx): return QSize(200, self.TH + 14)
    def paint(self, p, opt, idx):
        p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = opt.rect.adjusted(2, 1, -2, -1); sel = bool(opt.state & QStyle.StateFlag.State_Selected); hov = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        if sel or hov: p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(PAL["hover"] if sel else PAL["surface"])); p.drawRoundedRect(r, 10, 10)
        nf = QFont(opt.font); nf.setPixelSize(12); p.setFont(nf); p.setPen(QColor(PAL["text"] if sel else PAL["muted"]))
        p.drawText(QRect(r.left(), r.top(), 30, r.height()), Qt.AlignmentFlag.AlignCenter, "▶" if sel else str(idx.data(ROLE_NUM) or ""))
        tr = QRect(r.left() + 30, r.top() + (r.height() - self.TH) // 2, self.TW, self.TH)
        path = QPainterPath(); path.addRoundedRect(QRectF(tr), 8, 8); p.setClipPath(path)
        pm = idx.data(ROLE_THUMB)
        if isinstance(pm, QPixmap) and not pm.isNull():
            sc = pm.scaled(tr.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(tr.topLeft(), sc, QRect((sc.width() - tr.width()) // 2, (sc.height() - tr.height()) // 2, tr.width(), tr.height()))
        else:
            p.fillRect(tr, QColor(PAL["surface"] if not sel else PAL["border"])); p.setPen(QColor(PAL["muted"])); p.drawText(tr, Qt.AlignmentFlag.AlignCenter, "▶")
        prog = idx.data(ROLE_PROG) or 0
        if prog > 0:
            p.fillRect(QRect(tr.left(), tr.bottom() - 2, tr.width(), 3), QColor(255, 255, 255, 80))
            p.fillRect(QRect(tr.left(), tr.bottom() - 2, int(tr.width() * min(prog, 1)), 3), QColor(PAL["accent"]))
        p.setClipping(False)
        dur = idx.data(ROLE_DUR)
        if dur:
            bf = QFont(opt.font); bf.setPixelSize(11); bf.setBold(True); p.setFont(bf); w = QFontMetrics(bf).horizontalAdvance(dur) + 10
            br = QRect(tr.right() - w - 4, tr.bottom() - 24, w, 17); p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, 0, 0, 205)); p.drawRoundedRect(br, 4, 4)
            p.setPen(QColor("#ffffff")); p.drawText(br, Qt.AlignmentFlag.AlignCenter, dur)
        x = tr.right() + 12; w = r.right() - x - 6; y = tr.top()
        tf = QFont(opt.font); tf.setPixelSize(13); tf.setBold(True); fm = QFontMetrics(tf); p.setFont(tf); p.setPen(QColor(PAL["text"]))
        for ln in wrap2(fm, idx.data(ROLE_TITLE) or "", w): p.drawText(QRect(x, y, w, fm.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, ln); y += fm.height() + 1
        sf = QFont(opt.font); sf.setPixelSize(12); f2 = QFontMetrics(sf); p.setFont(sf); p.setPen(QColor(PAL["muted"])); y += 2
        for ln in (idx.data(ROLE_SUB) or []):
            if ln: p.drawText(QRect(x, y, w, f2.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f2.elidedText(ln, Qt.TextElideMode.ElideRight, w)); y += f2.height() + 1
        p.restore()

def fmt_views(n):
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= lim: return f"{n/lim:.1f}".rstrip("0").rstrip(".") + suf
    return str(n)
def ago(d):
    from datetime import date
    try: days = (date.today() - date.fromisoformat(d[:10])).days
    except Exception: return ""
    if days < 1: return "today"
    if days < 30: return f"{days}d ago"
    if days < 365: return f"{days // 30}mo ago"
    return f"{days // 365}y ago"
def nkey(p): return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", Path(p).name)]
def fmt(ms):
    s = max(0, int(ms // 1000)); h, r = divmod(s, 3600); m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

class ClickSlider(QSlider):
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            v = self.minimum() + (self.maximum() - self.minimum()) * e.position().x() / self.width()
            self.setValue(int(v)); self.sliderMoved.emit(int(v))
        super().mousePressEvent(e)

MINI_STYLE = """
QWidget#mini{background:#000;border:1px solid @@groove@@}
QWidget#bar{background:@@bg@@}
QPushButton{background:transparent;border:none;border-radius:6px;padding:2px 7px;font-size:13px;min-width:22px;color:@@btntext@@}
QPushButton:hover{background:@@border@@}
QSlider::groove:horizontal{height:3px;background:@@groove@@;border-radius:1px}
QSlider::sub-page:horizontal{background:@@accent@@;border-radius:1px}
QSlider::handle:horizontal{background:@@text@@;width:9px;height:9px;margin:-3px 0;border-radius:4px}
"""

class DragBar(QWidget):
    def __init__(self, p):
        super().__init__(p); self.setObjectName("bar"); self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    def mousePressEvent(self, e):
        wh = self.window().windowHandle()
        if e.button() == Qt.MouseButton.LeftButton and wh: wh.startSystemMove()

class Mini(QWidget):
    """Slim frameless always-on-top window. The control bar only appears while the mouse is over it."""
    def __init__(self, o):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.o = o; self.surface = None
        self.setObjectName("mini"); self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True); self.setStyleSheet(themed(MINI_STYLE))
        self.setWindowTitle("Mini player"); self.setWindowIcon(o.windowIcon()); self.setMinimumSize(240, 150)
        self.lay = QVBoxLayout(self); self.lay.setContentsMargins(1, 1, 1, 1); self.lay.setSpacing(0)
        def b(t, tip, f):
            x = QPushButton(t); x.setToolTip(tip); x.clicked.connect(f); x.setFocusPolicy(Qt.FocusPolicy.NoFocus); return x
        self.pb = b("▶", "Play / pause (Space)", o.mini_play)
        self.seek = ClickSlider(Qt.Orientation.Horizontal); self.seek.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.seek.sliderMoved.connect(o.mp.setPosition)
        self.bot = DragBar(self); h = QHBoxLayout(self.bot); h.setContentsMargins(6, 2, 2, 2); h.setSpacing(0)
        for w in (b("⏮", "Previous", o.prev), self.pb, b("⏭", "Next", o.next)): h.addWidget(w)
        h.addWidget(self.seek, 100); h.addStretch(1); h.addWidget(b("⤢", "Back to full player (I / Esc)", o.mini_toggle))
        h.addWidget(QSizeGrip(self), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.lay.addWidget(self.bot); self.bot.hide()
        self.hover = QTimer(self); self.hover.setInterval(250); self.hover.timeout.connect(self.check_hover)
        for k, f in {"Space": o.mini_play, "I": o.mini_toggle, "Esc": o.mini_toggle, "Left": lambda: o.skip(-OPT["step"]), "Right": lambda: o.skip(OPT["step"])}.items():
            QShortcut(QKeySequence(k), self, activated=f)
    def check_hover(self):
        self.bot.setVisible(self.geometry().contains(QCursor.pos()) or self.seek.isSliderDown())
    def showEvent(self, e): self.hover.start(); super().showEvent(e)
    def hideEvent(self, e): self.hover.stop(); super().hideEvent(e)
    def mousePressEvent(self, e):
        wh = self.windowHandle()
        if e.button() == Qt.MouseButton.LeftButton and wh: wh.startSystemMove()
    def closeEvent(self, e):
        e.ignore(); self.o.mini_toggle()

FS_STYLE = MINI_STYLE.replace("border:1px solid @@groove@@", "border:none") + "QPushButton{font-size:16px;padding:6px 12px}QLabel{background:transparent}"

class FullWin(QWidget):
    """Fullscreen window of its own: only the video shows. Local playback gets a control bar that hides when the mouse is idle."""
    def __init__(self, o):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.o = o; self.surface = None; self.local = True; self.idle = 0; self.lastpos = None
        self.setObjectName("mini"); self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True); self.setStyleSheet(themed(FS_STYLE))
        self.setWindowTitle("Playlist Player"); self.setWindowIcon(o.windowIcon())
        self.lay = QVBoxLayout(self); self.lay.setContentsMargins(0, 0, 0, 0); self.lay.setSpacing(0)
        def b(t, tip, f):
            x = QPushButton(t); x.setToolTip(tip); x.clicked.connect(f); x.setFocusPolicy(Qt.FocusPolicy.NoFocus); return x
        self.pb = b("▶", "Play / pause (Space)", o.mini_play)
        self.seek = ClickSlider(Qt.Orientation.Horizontal); self.seek.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.seek.sliderMoved.connect(o.mp.setPosition)
        self.time = QLabel("0:00 / 0:00")
        self.bar = QWidget(); self.bar.setObjectName("bar"); self.bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        h = QHBoxLayout(self.bar); h.setContentsMargins(16, 8, 16, 10); h.setSpacing(6)
        for w in (b("⏮", "Previous (P)", o.prev), self.pb, b("⏭", "Next (N)", o.next)): h.addWidget(w)
        h.addWidget(self.seek, 1); h.addWidget(self.time); h.addWidget(b("⛶", "Exit fullscreen (Esc)", o.exit_fs))
        self.lay.addWidget(self.bar); self.bar.hide()
        self.timer = QTimer(self); self.timer.setInterval(200); self.timer.timeout.connect(self.tick)
        for k, f in {"Esc": o.exit_fs, "F": o.exit_fs, "F11": o.exit_fs, "Space": o.mini_play, "K": o.mini_play, "Left": lambda: o.skip(-OPT["step"]),
                     "Right": lambda: o.skip(OPT["step"]), "J": lambda: o.skip(-2 * OPT["step"]), "L": lambda: o.skip(2 * OPT["step"]),
                     "Up": lambda: o.volstep(5), "Down": lambda: o.volstep(-5), "N": o.next, "P": o.prev, "M": o.mute}.items():
            QShortcut(QKeySequence(k), self, activated=f)
    def tick(self):
        p = QCursor.pos()
        if p != self.lastpos: self.lastpos = p; self.idle = 0
        else: self.idle += 200
        show = self.local and (self.idle < 2500 or self.seek.isSliderDown())
        if self.bar.isVisible() != show: self.bar.setVisible(show)
        self.setCursor(Qt.CursorShape.ArrowCursor if (show or not self.local) else Qt.CursorShape.BlankCursor)
    def showEvent(self, e): self.idle = 0; self.timer.start(); super().showEvent(e)
    def hideEvent(self, e): self.timer.stop(); self.unsetCursor(); super().hideEvent(e)
    def closeEvent(self, e): e.ignore(); self.o.exit_fs()

class Player(QMainWindow):
    update_found = pyqtSignal(str, str)
    title_found = pyqtSignal(str, str, str)
    stats_found = pyqtSignal(str)
    thumb_found = pyqtSignal(str)
    dl_progress = pyqtSignal(int)
    dl_done = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Playlist Player"); self.setAcceptDrops(True)
        self.cfg = QSettings("PlaylistPlayer", "PlaylistPlayer")
        self.tmp = None; self.files = []; self.idx = -1; self.order = []
        self.pos = json.loads(self.cfg.value("positions", "{}")); self.watched = set(json.loads(self.cfg.value("watched", "[]")))
        self.repeat = 0
        self.yt_watched = set(json.loads(self.cfg.value("yt_watched", "[]"))); self.yt_titles = json.loads(self.cfg.value("yt_titles", "{}")); self.yt_stats = json.loads(self.cfg.value("yt_stats", "{}"))
        self.yt_ids = []; self.yt_cur = -1; self.yt_pid = ""; self._was_fs = False; self.yt_failed = set()
        self.yt_pos = json.loads(self.cfg.value("yt_pos", "{}")); self.yt_last_t = 0; self.yt_first = False; self.durs = json.loads(self.cfg.value("durs", "{}")); self.chip_mode = 0
        self.thumb_dir = str(Path.home() / ".playlistplayer" / "thumbs"); os.makedirs(self.thumb_dir, exist_ok=True)
        self.yt_timer = QTimer(interval=1000); self.yt_timer.timeout.connect(self.yt_poll)
        self.audio = QAudioOutput(); self.mp = QMediaPlayer(); self.mp.setAudioOutput(self.audio)
        self.audio.setVolume(float(self.cfg.value("volume", 0.8)))
        self.video = QVideoWidget(); self.mp.setVideoOutput(self.video)
        self.video.installEventFilter(self)
        self.mini = Mini(self); self.fsw = FullWin(self)

        # sidebar
        self.search = QLineEdit(); self.search.setPlaceholderText("Search"); self.search.setObjectName("search"); self.search.textChanged.connect(self.filter)
        self.list = QListWidget(); self.list.setItemDelegate(VideoDelegate(self)); self.list.setMouseTracking(True); self.list.itemClicked.connect(lambda it: self.play(it.data(Qt.ItemDataRole.UserRole)))
        self.info = QLabel("Drop a folder or .zip here"); self.info.setWordWrap(True); self.info.setObjectName("nowMeta")
        openb = QPushButton("📁  Open folder"); openb.setObjectName("pill"); openb.clicked.connect(self.open_folder)
        more = QPushButton("⋯"); more.setObjectName("icon"); more.setToolTip("More"); mm = QMenu(self)
        mm.addAction("Appearance & settings…", self.open_settings); mm.addAction("Open zip…", self.open_zip); mm.addAction("Clear extracted zips", self.clear_zips); mm.addAction("YouTube API key…", self.set_key)
        mm.addAction(f"Check for updates (v{__version__})", lambda: self.check_update(True)); mm.addAction("Update source (GitHub repo)…", self.set_update_repo); more.setMenu(mm)
        self.ytb = QPushButton("▶  YouTube mode"); self.ytb.setObjectName("pill"); self.ytb.setToolTip("Plays in YouTube's official player, so views count"); self.ytb.setCheckable(True); self.ytb.clicked.connect(self.yt_toggle)
        minib = QPushButton("◱"); minib.setObjectName("icon"); minib.setToolTip("Mini player (I)"); minib.clicked.connect(self.mini_toggle)
        self.chips = []; self.chipbar = QWidget(); cb = QHBoxLayout(self.chipbar); cb.setContentsMargins(0, 0, 0, 0); cb.setSpacing(8)
        for i, nm in enumerate(("All", "Unwatched", "Watched")):
            c = QPushButton(nm); c.setObjectName("pill"); c.setCheckable(True); c.setChecked(i == 0); c.clicked.connect(lambda _=False, i=i: self.set_chip(i)); self.chips.append(c); cb.addWidget(c)
        cb.addStretch(1)
        side = QWidget(); sl = QVBoxLayout(side); sl.setContentsMargins(12, 12, 12, 12); sl.setSpacing(8)
        self.ytlist = QListWidget(); self.ytlist.setItemDelegate(VideoDelegate(self)); self.ytlist.setMouseTracking(True); self.ytlist.hide(); self.ytlist.itemClicked.connect(self.yt_play_item)
        self.head = QLabel("Local files"); self.head.setObjectName("head")
        for w in (self.head, self.info, self.chipbar, self.list, self.ytlist): sl.addWidget(w)
        side.setObjectName("side"); side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True); side.setMinimumWidth(390); self.side = side

        # controls
        def btn(t, tip, f, chk=False):
            b = QPushButton(t); b.setToolTip(tip); b.clicked.connect(f); b.setCheckable(chk); b.setFocusPolicy(Qt.FocusPolicy.NoFocus); b.setMinimumWidth(38); return b
        self.pbtn = btn("▶", "Play/Pause (Space)", self.toggle); self.pbtn.setObjectName("play")
        self.seek = ClickSlider(Qt.Orientation.Horizontal); self.seek.sliderMoved.connect(self.mp.setPosition); self.seek.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.time = QLabel("0:00 / 0:00")
        self.speed = QComboBox(); self.speed.addItems([f"{s}x" for s in SPEEDS]); self.speed.setCurrentIndex(SPEEDS.index(float(self.cfg.value("speed", 1.0))))
        self.speed.currentIndexChanged.connect(self.set_speed); self.speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol = QSlider(Qt.Orientation.Horizontal); self.vol.setRange(0, 100); self.vol.setFixedWidth(90); self.vol.setValue(int(self.audio.volume() * 100))
        self.vol.valueChanged.connect(lambda v: self.audio.setVolume(v / 100)); self.vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.shuf = btn("⇄", "Shuffle (S)", self.rebuild_order, True)
        self.rep = btn("↻", "Repeat: off (R)", self.cycle_repeat, True)
        self.auto = btn("⇥", "Auto-play next video", lambda: None, True); self.auto.setChecked(True)
        self.sleep = btn("☾", "Sleep timer: click to cycle off/15/30/60 min", self.cycle_sleep, True)
        self.sleep_min = 0; self.sleep_timer = QTimer(singleShot=True); self.sleep_timer.timeout.connect(lambda: (self.mp.pause(), self.flash("Sleep timer: paused")))
        bar = QHBoxLayout()
        for w in (btn("⏮", "Previous (P)", self.prev), self.pbtn, btn("⏭", "Next (N)", self.next), self.seek, self.time, self.speed,
                  btn("🔊", "Mute (M)", self.mute), self.vol, self.shuf, self.rep, self.auto, self.sleep,
                  btn("◱", "Mini player (I)", self.mini_toggle), btn("☰", "Toggle playlist (T)", self.toggle_side), btn("⛶", "Fullscreen (F)", self.fullscreen)):
            bar.addWidget(w, 1 if w is self.seek else 0)
        self.controls = QWidget(); self.controls.setObjectName("controls"); bar.setContentsMargins(14, 8, 14, 10); bar.setSpacing(4); self.controls.setLayout(bar)
        self.osd = QLabel("", self.video); self.osd.setStyleSheet("background:rgba(0,0,0,170);color:#fff;padding:8px 14px;border-radius:8px;font-size:16px"); self.osd.hide()
        self.osd_t = QTimer(singleShot=True, interval=1200); self.osd_t.timeout.connect(self.osd.hide)

        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(20, 12, 0, 0); ll.setSpacing(0); self.stack = QStackedWidget(); self.stack.addWidget(self.video); self.web = None; ll.addWidget(self.stack, 1)
        self.strip = QWidget(); sv = QVBoxLayout(self.strip); sv.setContentsMargins(4, 14, 4, 10); sv.setSpacing(10)
        self.now_title = QLabel(); self.now_title.setObjectName("nowTitle"); self.now_title.setWordWrap(True)
        self.avatar = QLabel("?"); self.avatar.setObjectName("avatar"); self.now_author = QLabel(); self.now_author.setObjectName("author")
        arow = QHBoxLayout(); arow.setSpacing(12); arow.addWidget(self.avatar); arow.addWidget(self.now_author); arow.addStretch(1)
        self.now_meta = QLabel(); self.now_meta.setObjectName("desc"); self.now_meta.setWordWrap(True)
        sv.addWidget(self.now_title); sv.addLayout(arow); sv.addWidget(self.now_meta); self.show_local()
        ll.addWidget(self.controls); ll.addWidget(self.strip)
        self.leftw = left; sp = QSplitter(); sp.addWidget(left); sp.addWidget(side); sp.setStretchFactor(0, 1); sp.setSizes([980, 300]); gear = QPushButton("⚙"); gear.setObjectName("icon"); gear.setToolTip("Appearance & settings (Ctrl+,)"); gear.clicked.connect(self.open_settings)
        logo = QLabel(); logo.setPixmap(self.windowIcon().pixmap(30, 30)); brand = QLabel("Playlist Player"); brand.setObjectName("brand")
        sbtn = QPushButton("🔍"); sbtn.setObjectName("searchbtn"); sbtn.clicked.connect(self.filter)
        self.header = QWidget(); hh = QHBoxLayout(self.header); hh.setContentsMargins(20, 8, 20, 8); hh.setSpacing(8)
        hh.addWidget(logo); hh.addWidget(brand); hh.addStretch(1)
        sbox = QHBoxLayout(); sbox.setSpacing(0); sbox.addWidget(self.search, 1); sbox.addWidget(sbtn); hh.addLayout(sbox, 6); hh.addStretch(1)
        for w in (openb, self.ytb, minib, gear, more): hh.addWidget(w)
        cw = QWidget(); cv = QVBoxLayout(cw); cv.setContentsMargins(0, 0, 20, 16); cv.setSpacing(0); cv.addWidget(self.header); cv.addWidget(sp); self.setCentralWidget(cw)
        self.sp = sp

        self.mp.positionChanged.connect(self.on_pos); self.mp.durationChanged.connect(lambda d: (self.seek.setRange(0, d), self.mini.seek.setRange(0, d), self.fsw.seek.setRange(0, d), self.on_dur(d)))
        self.mp.playbackStateChanged.connect(self.on_state)
        self.mp.mediaStatusChanged.connect(self.on_status); self.mp.errorOccurred.connect(self.on_error)
        self.hide_t = QTimer(singleShot=True, interval=2500); self.hide_t.timeout.connect(self.autohide)
        QApplication.instance().installEventFilter(self)
        self.save_t = QTimer(interval=5000); self.save_t.timeout.connect(self.save); self.save_t.start()

        for k, f in {"Space": self.toggle, "K": self.toggle, "Left": lambda: self.skip(-OPT["step"]), "Right": lambda: self.skip(OPT["step"]), "J": lambda: self.skip(-2 * OPT["step"]),
                     "L": lambda: self.skip(2 * OPT["step"]), "Up": lambda: self.volstep(5), "Down": lambda: self.volstep(-5), "F": self.fullscreen, "Esc": self.exit_fs,
                     "N": self.next, "P": self.prev, "M": self.mute, "S": lambda: self.shuf.click(), "R": self.cycle_repeat, "T": self.toggle_side,
                     "]": lambda: self.step_speed(1), "[": lambda: self.step_speed(-1), "Ctrl+O": self.open_folder, "I": self.mini_toggle, "F11": self.fullscreen, "Ctrl+,": self.open_settings, "Ctrl+F": lambda: self.search.setFocus()}.items():
            QShortcut(QKeySequence(k), self, activated=f)
        for d in range(10): QShortcut(QKeySequence(str(d)), self, activated=lambda d=d: self.mp.setPosition(int(self.mp.duration() * d / 10)))
        g = self.cfg.value("geometry")
        if g: self.restoreGeometry(g)
        else: self.resize(1280, 760)
        self.update_found.connect(self.on_update); self.title_found.connect(self.on_title); self.stats_found.connect(self.on_stats); self.thumb_found.connect(self.on_thumb); self.dl_progress.connect(self.on_dl_progress); self.dl_done.connect(self.on_dl_done); QTimer.singleShot(4000, self.check_update); self.layout_side(); self.apply_opts()
        last = self.cfg.value("source")
        if last and os.path.isdir(last): self.load_dir(last)
        elif len(sys.argv) > 1: self.load_path(sys.argv[1])
        if self.cfg.value("mode") == "yt" and self.cfg.value("yt_pl") and QWebEngineView is not None: QTimer.singleShot(500, self.yt_resume)

    # ---- loading
    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choose video folder", self.cfg.value("source", ""))
        if d: self.load_dir(d)
    def open_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose zip", "", "Zip (*.zip)")
        if f: self.load_zip(f)
    def load_path(self, p):
        if os.path.isdir(p): self.load_dir(p)
        elif p.lower().endswith(".zip"): self.load_zip(p)
        elif Path(p).suffix.lower() in EXTS: self.load_dir(os.path.dirname(p), start=p)
    def load_zip(self, f):
        import hashlib
        st = os.stat(f); key = hashlib.md5(f"{f}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:12]
        d = str(Path.home() / ".playlistplayer" / "zips" / key)      # stable folder, so progress survives restarts
        if not os.path.isdir(d):
            self.info.setText("Extracting…"); QApplication.processEvents()
            with zipfile.ZipFile(f) as z: z.extractall(d + ".part")
            os.rename(d + ".part", d)
        self.load_dir(d)
    def load_dir(self, d, start=None, remember=True):
        fs = [str(p) for p in Path(d).rglob("*") if p.suffix.lower() in EXTS]
        fs.sort(key=nkey); self.files = fs
        if remember: self.cfg.setValue("source", d)
        self.list.clear()
        for i, f in enumerate(fs):
            it = QListWidgetItem(); it.setData(Qt.ItemDataRole.UserRole, i); self.list.addItem(it)
        self.refresh_items(); self.rebuild_order()
        if not fs: self.info.setText("No videos found."); return
        last = self.cfg.value("last_file")
        i = fs.index(start) if start in fs else (fs.index(last) if last in fs else 0)
        self.play(i, autostart=False)
    def refresh_items(self):
        for r in range(self.list.count()):
            it = self.list.item(r); i = it.data(Qt.ItemDataRole.UserRole); f = self.files[i]
            d = self.durs.get(f, 0); p = self.pos.get(f, 0); done = f in self.watched; stem = Path(f).stem
            it.setText(stem); it.setData(ROLE_TITLE, stem); it.setData(ROLE_NUM, i + 1); it.setData(ROLE_DONE, done)
            it.setData(ROLE_SUB, [Path(f).parent.name or "Local file", "Watched" if done else (f"Resume at {fmt(p)}" if p > 10000 else "")])
            it.setData(ROLE_DUR, fmt(d) if d else ""); it.setData(ROLE_PROG, 1.0 if done else (min(1.0, p / d) if d and p > 10000 else 0.0))
    def set_chip(self, i):
        self.chip_mode = i
        for k, c in enumerate(self.chips): c.setChecked(k == i)
        self.filter()
    def filter(self, *_):
        t = self.search.text().lower(); lst = self.ytlist if self.ytb.isChecked() else self.list
        for r in range(lst.count()):
            it = lst.item(r); done = bool(it.data(ROLE_DONE))
            it.setHidden(not (t in it.text().lower() and (self.chip_mode == 0 or (self.chip_mode == 1 and not done) or (self.chip_mode == 2 and done))))
    def rebuild_order(self):
        self.order = list(range(len(self.files)))
        if self.shuf.isChecked(): random.shuffle(self.order)
        self.flash("Shuffle on" if self.shuf.isChecked() else "Shuffle off")

    # ---- playback
    def play(self, i, autostart=True):
        if not (0 <= i < len(self.files)): return
        self.idx = i; f = self.files[i]; self.cfg.setValue("last_file", f)
        self.mp.setSource(QUrl.fromLocalFile(f)); self.mp.setPlaybackRate(SPEEDS[self.speed.currentIndex()])
        self._resume = self.pos.get(f, 0) if OPT["resume"] else 0
        self.list.setCurrentRow(i); self.setWindowTitle(f"{Path(f).stem} — Playlist Player"); self.show_local(); self.refresh_items()
        self.info.setText(f"{i+1} of {len(self.files)} · {sum(x in self.watched for x in self.files)} watched")
        if autostart: self.mp.play()
    def on_status(self, s):
        M = QMediaPlayer.MediaStatus
        if s == M.LoadedMedia and getattr(self, "_resume", 0) > 5000:
            self.mp.setPosition(self._resume); self.flash(f"Resumed at {fmt(self._resume)}"); self._resume = 0
        if s == M.EndOfMedia:
            self.watched.add(self.files[self.idx]); self.pos.pop(self.files[self.idx], None); self.refresh_items()
            if self.repeat == 2: self.mp.setPosition(0); self.mp.play()
            elif self.auto.isChecked(): self.next(wrap=self.repeat == 1)
    def on_error(self, *a):
        self.flash("Can't play this file, skipping…"); QTimer.singleShot(1500, self.next)
    def on_pos(self, p):
        if not self.seek.isSliderDown(): self.seek.setValue(p)
        if self.mini.isVisible() and not self.mini.seek.isSliderDown(): self.mini.seek.setValue(p)
        if self.fsw.isVisible():
            if not self.fsw.seek.isSliderDown(): self.fsw.seek.setValue(p)
            self.fsw.time.setText(f"{fmt(p)} / {fmt(self.mp.duration())}")
        self.time.setText(f"{fmt(p)} / {fmt(self.mp.duration())}")
        d = self.mp.duration()
        if 0 <= self.idx < len(self.files) and d > 0:
            f = self.files[self.idx]; self.pos[f] = p
            if p > d * 0.92 and f not in self.watched: self.watched.add(f); self.refresh_items()
    def toggle(self):
        if self.ytb.isChecked(): return
        self.mp.pause() if self.mp.playbackState() == QMediaPlayer.PlaybackState.PlayingState else self.mp.play()
    def next(self, wrap=False):
        if self.ytb.isChecked(): self.yt_cmd("p.nextVideo()"); return
        if not self.order: return
        k = self.order.index(self.idx) + 1
        if k >= len(self.order):
            if not (wrap or self.repeat == 1): return
            k = 0
        self.play(self.order[k])
    def prev(self):
        if self.ytb.isChecked(): self.yt_cmd("p.previousVideo()"); return
        if not self.order: return
        if self.mp.position() > 4000: self.mp.setPosition(0); return
        self.play(self.order[max(0, self.order.index(self.idx) - 1)])
    def skip(self, s):
        if self.ytb.isChecked(): return
        self.mp.setPosition(max(0, self.mp.position() + s * 1000)); self.flash(f"{'+' if s > 0 else ''}{s}s")
    def volstep(self, d): self.vol.setValue(self.vol.value() + d); self.flash(f"Volume {self.vol.value()}%")
    def mute(self): self.audio.setMuted(not self.audio.isMuted()); self.flash("Muted" if self.audio.isMuted() else "Unmuted")
    def set_speed(self, i): self.mp.setPlaybackRate(SPEEDS[i]); self.cfg.setValue("speed", SPEEDS[i]); self.flash(f"Speed {SPEEDS[i]}x")
    def step_speed(self, d): self.speed.setCurrentIndex(min(len(SPEEDS) - 1, max(0, self.speed.currentIndex() + d)))
    def cycle_repeat(self):
        self.repeat = (self.repeat + 1) % 3; n = ["off", "all", "one"][self.repeat]; self.rep.setToolTip(f"Repeat: {n} (R)"); self.rep.setChecked(self.repeat > 0); self.flash(f"Repeat {n}")
    def cycle_sleep(self):
        self.sleep_min = {0: 15, 15: 30, 30: 60, 60: 0}[self.sleep_min]; self.sleep_timer.stop()
        if self.sleep_min: self.sleep_timer.start(self.sleep_min * 60000)
        self.sleep.setChecked(bool(self.sleep_min)); self.flash(f"Sleep in {self.sleep_min} min" if self.sleep_min else "Sleep timer off")

    # ---- YouTube mode (official embed: views count, YouTube's ads/Premium rules apply)
    def yt_toggle(self):
        if self.mini.isVisible(): self.mini_toggle()
        if not self.ytb.isChecked():
            self.yt_off(); return
        if QWebEngineView is None:
            self.ytb.setChecked(False); QMessageBox.warning(self, "Missing", "Install PyQt6-WebEngine (build.bat does this)."); return
        rec = json.loads(self.cfg.value("yt_recent", json.dumps([YT_PLAYLIST]))); base = "https://www.youtube.com/playlist?list="
        t = self.ask("Add a YouTube playlist", "Paste a playlist link (or just its ID). It plays in YouTube's own player, so views still count.",
                     base + self.cfg.value("yt_pl", YT_PLAYLIST), [base + x for x in rec], base + "…") or ""
        m = re.search(r"list=([\w-]+)", t); pid = m.group(1) if m else (t if re.fullmatch(r"[\w-]+", t) else None)
        if not pid: self.ytb.setChecked(False); return
        if pid in rec: rec.remove(pid)
        rec.insert(0, pid); self.cfg.setValue("yt_recent", json.dumps(rec[:8])); self.yt_enter(pid)
    def yt_enter(self, pid):
        self.cfg.setValue("yt_pl", pid); self.mp.pause()
        if not self.web:
            prof = QWebEngineProfile("ytplayer", self)   # persistent: stays signed in between launches
            page = QWebEnginePage(prof, self); st = page.settings()
            st.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
            st.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
            page.fullScreenRequested.connect(self.yt_fs)
            self.web = QWebEngineView(); self.web.setPage(page); self.stack.addWidget(self.web)
        self.yt_start(pid)
        self.stack.setCurrentWidget(self.web); self.controls.hide()
    def yt_resume(self): self.ytb.setChecked(True); self.yt_enter(self.cfg.value("yt_pl"))
    def ask(self, title, label, text="", items=None, ph=""):
        d = QDialog(self); d.setWindowTitle(title); d.setMinimumWidth(680)
        lay = QVBoxLayout(d); lay.setContentsMargins(26, 24, 26, 20); lay.setSpacing(12)
        h = QLabel(title); h.setObjectName("head"); l = QLabel(label); l.setWordWrap(True); l.setObjectName("nowMeta"); lay.addWidget(h); lay.addWidget(l)
        if items: w = QComboBox(); w.setEditable(True); w.addItems(items); w.setCurrentText(text); le = w.lineEdit()
        else: w = le = QLineEdit(text)
        le.setPlaceholderText(ph); w.setMinimumHeight(40); lay.addWidget(w)
        row = QHBoxLayout(); paste = QPushButton("Paste from clipboard"); paste.clicked.connect(lambda: le.setText(QApplication.clipboard().text().strip()))
        ok = QPushButton("OK"); ok.setObjectName("primary"); ok.setDefault(True); ok.clicked.connect(d.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(d.reject)
        row.addWidget(paste); row.addStretch(1); row.addWidget(cancel); row.addWidget(ok); lay.addSpacing(6); lay.addLayout(row)
        le.selectAll(); le.setFocus()
        return le.text().strip() if d.exec() else None

    def yt_thumbs(self, ids):
        from concurrent.futures import ThreadPoolExecutor
        def one(v):
            f = os.path.join(self.thumb_dir, v + ".jpg")
            if not os.path.exists(f):
                try:
                    data = urllib.request.urlopen(urllib.request.Request(f"https://i.ytimg.com/vi/{v}/mqdefault.jpg", headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read()
                    open(f, "wb").write(data)
                except Exception: return
            self.thumb_found.emit(v)
        with ThreadPoolExecutor(6) as ex: list(ex.map(one, ids))
    def on_thumb(self, v):
        pm = QPixmap(os.path.join(self.thumb_dir, v + ".jpg"))
        if pm.isNull() or not OPT["thumbs"]: return
        for k, x in enumerate(self.yt_ids):
            it = self.ytlist.item(k) if x == v else None
            if it: it.setData(ROLE_THUMB, pm)
        self.ytlist.viewport().update()

    # ---- YouTube playlist sidebar (playback stays in YouTube's official player)
    PAGE = """<html><head><style>html,body,#p{margin:0;height:100%;background:#000}</style></head><body><div id="p"></div>
<script src="https://www.youtube.com/iframe_api"></script>
<script>
var p;
function onYouTubeIframeAPIReady(){
  p=new YT.Player('p',{width:'100%',height:'100%',playerVars:{autoplay:1,rel:0},
    events:{onReady:function(){p.loadPlaylist({listType:'playlist',list:'__PID__',index:__START__,startSeconds:__TS__});}}});
}
</script></body></html>"""
    def yt_start(self, pid):
        self.yt_pid = pid; self.yt_ids = []; self.yt_cur = -1
        same = self.cfg.value("yt_idx_for") == pid
        start = int(self.cfg.value("yt_idx", 0)) if same else 0; ts = max(0, int(float(self.cfg.value("yt_time", 0))) - 3) if same and OPT["resume"] else 0
        self.yt_first = True; self.yt_last_t = 0
        self.web.setHtml(self.PAGE.replace("__PID__", pid).replace("__START__", str(start)).replace("__TS__", str(ts)), QUrl("https://playlist-player.app/"))
        threading.Thread(target=self.yt_plmeta, args=(pid,), daemon=True).start()
        self.ytlist.clear(); self.list.hide(); self.ytlist.show(); self.search.clear(); self.info.setText("Loading playlist…"); self.head.setText("YouTube playlist")
        self.yt_timer.start()
    def yt_off(self):
        self.yt_timer.stop(); self.stack.setCurrentWidget(self.video); self.web.setHtml("")
        self.controls.show(); self.side.show(); self.ytlist.hide(); self.list.show(); self.search.clear(); self.setWindowTitle("Playlist Player"); self.head.setText("Local files"); self.show_local()
        self.info.setText(f"{self.idx+1} of {len(self.files)}" if self.files else "Drop a folder or .zip here")
    def yt_cmd(self, js):
        if self.web: self.web.page().runJavaScript(js)
    def yt_poll(self):
        if self.web: self.web.page().runJavaScript("(window.p&&p.getPlaylist&&p.getPlaylist())?JSON.stringify({ids:p.getPlaylist(),i:p.getPlaylistIndex(),s:p.getPlayerState(),t:p.getCurrentTime(),D:p.getDuration()}):''", self.yt_got)
    def yt_got(self, r):
        if not r: return
        d = json.loads(r); ids = d.get("ids") or []
        if ids and ids != self.yt_ids:
            self.yt_ids = ids; self.ytlist.clear()
            for _ in ids: self.ytlist.addItem(QListWidgetItem())
            self.yt_cur = -1
            for k in range(len(ids)): self.yt_label(k)
            todo = [v for v in dict.fromkeys(ids) if v not in self.yt_titles]
            if todo: threading.Thread(target=self.yt_fetch_titles, args=(todo,), daemon=True).start()
            if OPT["thumbs"]: threading.Thread(target=self.yt_thumbs, args=(list(dict.fromkeys(ids)),), daemon=True).start()
            threading.Thread(target=self.yt_crawl, args=(list(dict.fromkeys(ids)), self.cfg.value("yt_key", "")), daemon=True).start()
        i = d.get("i")
        if ids and i is not None and 0 <= i < len(ids):
            v, t, st_ = ids[i], d.get("t") or 0, d.get("s"); D = int(d.get("D") or 0)
            if D > 0 and self.yt_stats.get(v, {}).get("len") != D: self.yt_stats.setdefault(v, {})["len"] = D; self.yt_label(i)
            if st_ == 0: self.yt_pos.pop(v, None)
            elif st_ in (1, 2) and i == self.yt_cur and t > 5: self.yt_pos[v] = t; self.yt_last_t = t
            if d.get("s") == 0 and ids[i] not in self.yt_watched: self.yt_watched.add(ids[i]); self.yt_label(i)
            if i != self.yt_cur:
                prev = self.yt_cur; self.yt_cur = i; self.ytlist.setCurrentRow(i); self.cfg.setValue("yt_idx", i); self.cfg.setValue("yt_idx_for", self.yt_pid)
                self.info.setText(f"{getattr(self, 'pl_author', '')}  ·  {i+1} / {len(ids)}  ·  {sum(x in self.yt_watched for x in ids)} watched".strip(" ·"))
                self.yt_last_t = 0; saved = self.yt_pos.get(v, 0)
                if prev >= 0: self.yt_label(prev)
                if self.yt_first: self.yt_first = False
                elif saved > 10 and OPT["resume"]: self.yt_cmd(f"p.seekTo({saved},true)")      # jump back to where you left that video
                self.yt_show(ids[i]); threading.Thread(target=self.yt_stat_one, args=(ids[i], 3600, self.cfg.value("yt_key", "")), daemon=True).start()
    def yt_label(self, k):
        it = self.ytlist.item(k)
        if not it: return
        v = self.yt_ids[k]; st = self.yt_stats.get(v, {}); title = self.yt_titles.get(v, "Loading…"); done = v in self.yt_watched
        pos = self.yt_pos.get(v, 0); ln = st.get("len", 0); au = st.get("author", "")
        l2 = "  ·  ".join(x for x in (f"{fmt_views(st['views'])} views" if "views" in st else "", ago(st["date"]) if st.get("date") else "") if x)
        it.setText(f"{title} {au}"); it.setData(ROLE_TITLE, title); it.setData(ROLE_SUB, [au, l2]); it.setData(ROLE_NUM, k + 1); it.setData(ROLE_DONE, done)
        it.setData(ROLE_DUR, fmt(ln * 1000) if ln else ""); it.setData(ROLE_PROG, 1.0 if done else (min(1.0, pos / ln) if ln and pos > 10 else 0.0))
    def yt_fetch_titles(self, ids):
        from concurrent.futures import ThreadPoolExecutor
        def one(v):
            try:
                u = "https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v=" + v
                j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10)); return v, j.get("title", ""), j.get("author_name", "")
            except Exception: return v, "", ""
        with ThreadPoolExecutor(8) as ex:
            for v, t, a in ex.map(one, ids): self.title_found.emit(v, t, a)
    def on_title(self, v, t, a):
        if v.startswith("PL:"):
            self.pl_author = a; self.head.setText(t or "YouTube playlist"); return
        self.yt_titles[v] = t or "Unavailable video"
        if a: self.yt_stats.setdefault(v, {})["author"] = a
        for k, x in enumerate(self.yt_ids):
            if x == v: self.yt_label(k)
        if v == self.cur_id(): self.yt_show(v)
    def cur_id(self): return self.yt_ids[self.yt_cur] if 0 <= self.yt_cur < len(self.yt_ids) else ""
    def on_stats(self, v):
        for k, x in enumerate(self.yt_ids):
            if x == v: self.yt_label(k)
        if v == self.cur_id(): self.yt_show(v)
    def yt_show(self, v):
        st = self.yt_stats.get(v, {}); t = self.yt_titles.get(v, "")
        au = st.get("author", ""); bits = []
        if "views" in st: bits.append(f"{st['views']:,} views")
        if st.get("date"): bits.append(f"{ago(st['date'])}  ·  {st['date']}")
        if v in self.yt_failed and "views" not in st: bits.append("Views and upload date unavailable. Add a YouTube API key under the ⋯ menu.")
        self.now_title.setText(t or "Loading…"); self.now_author.setText(au or "…"); self.avatar.setText((au or "?")[:1].upper())
        self.now_meta.setText("     ".join(bits) or "Loading stats…")
        if t: self.setWindowTitle(f"{t} — Playlist Player")
    def show_local(self):
        if 0 <= self.idx < len(self.files):
            f = self.files[self.idx]; self.now_title.setText(Path(f).stem); self.now_author.setText(Path(f).parent.name or "Local file"); self.avatar.setText("▶")
            self.now_meta.setText(f"Local file     {os.path.getsize(f)/1e6:.0f} MB     video {self.idx+1} of {len(self.files)}")
        else:
            self.now_title.setText("Nothing playing"); self.now_author.setText("Playlist Player"); self.avatar.setText("▶"); self.now_meta.setText("Open a folder, or switch on YouTube mode.")
    def set_key(self):
        t = self.ask("YouTube API key", "Optional. Paste a YouTube Data API v3 key for reliable views and upload dates. Leave it empty to remove the key.", self.cfg.value("yt_key", ""), None, "AIza…")
        if t is None: return
        self.cfg.setValue("yt_key", t.strip()); self.yt_failed.clear()
        self.yt_stats = {k: {**x, "t": 0} for k, x in dict(self.yt_stats).items()}
        QMessageBox.information(self, "Saved", "Turn YouTube mode off and on again to refresh the stats.")
    def yt_api(self, ids, key):
        ok = False
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            try:
                u = "https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics,contentDetails&id=" + ",".join(chunk) + "&key=" + key
                for it in json.load(urllib.request.urlopen(u, timeout=15)).get("items", []):
                    v = it["id"]; sn = it["snippet"]; stt = it.get("statistics", {}); st = dict(self.yt_stats.get(v, {}))
                    st.update(author=sn.get("channelTitle", ""), date=sn.get("publishedAt", "")[:10], t=time.time())
                    if "viewCount" in stt: st["views"] = int(stt["viewCount"])
                    m2 = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", it.get("contentDetails", {}).get("duration", ""))
                    if m2: st["len"] = int(m2.group(1) or 0) * 3600 + int(m2.group(2) or 0) * 60 + int(m2.group(3) or 0)
                    self.yt_stats[v] = st; self.yt_failed.discard(v); self.stats_found.emit(v)
                ok = True
            except Exception:
                self.yt_failed.update(chunk)
                for v in chunk: self.stats_found.emit(v)
        return ok
    def yt_stat_one(self, v, max_age, key=""):
        if time.time() - self.yt_stats.get(v, {}).get("t", 0) < max_age: return None
        if key: return self.yt_api([v], key)
        try:
            rq = urllib.request.Request("https://www.youtube.com/watch?v=" + v, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                                                                                        "Accept-Language": "en-GB,en;q=0.9", "Cookie": "SOCS=CAI; CONSENT=YES+1"})
            h = urllib.request.urlopen(rq, timeout=15).read().decode("utf-8", "ignore")
            m = re.search(r'"viewCount":"(\d+)"', h); d = re.search(r'"(?:publishDate|uploadDate)":"(\d{4}-\d\d-\d\d)', h); a = re.search(r'"author":"((?:[^"\\]|\\.)*)"', h)
            if m or d:
                st = dict(self.yt_stats.get(v, {}))
                if m: st["views"] = int(m.group(1))
                if d: st["date"] = d.group(1)
                ls = re.search(r'"lengthSeconds":"(\d+)"', h)
                if ls: st["len"] = int(ls.group(1))
                if a:
                    try: st["author"] = json.loads('"' + a.group(1) + '"')
                    except Exception: pass
                st["t"] = time.time(); self.yt_stats[v] = st; self.stats_found.emit(v); return True
        except Exception: pass
        self.yt_failed.add(v); self.stats_found.emit(v); return False
    def yt_crawl(self, ids, key=""):
        if key:
            self.yt_api([v for v in ids if time.time() - self.yt_stats.get(v, {}).get("t", 0) > 86400], key); return
        fails = 0
        for v in ids:
            r = self.yt_stat_one(v, 7 * 86400)
            if r: fails = 0; time.sleep(0.4)
            elif r is False:
                fails += 1
                if fails >= 5: break          # blocked: stop instead of hammering YouTube
    def yt_play_item(self, it): self.yt_cmd(f"p.playVideoAt({self.ytlist.row(it)})")

    # ---- appearance & settings
    def layout_side(self):
        left = OPT["side"] == "left"
        self.sp.insertWidget(0 if left else 1, self.side)
        self.sp.setStretchFactor(self.sp.indexOf(self.leftw), 1); self.sp.setStretchFactor(self.sp.indexOf(self.side), 0)
        self.sp.setHandleWidth(14); self.sp.setSizes([420, 980] if left else [980, 420])
    def apply_opts(self):
        QApplication.instance().setStyleSheet(themed(STYLE)); self.mini.setStyleSheet(themed(MINI_STYLE)); self.fsw.setStyleSheet(themed(FS_STYLE))
        self.mini.setWindowOpacity(OPT["mini_opacity"] / 100)
        if not OPT["thumbs"]:
            for k in range(self.ytlist.count()): self.ytlist.item(k).setData(ROLE_THUMB, None)
        self.ytlist.viewport().update()
        pal = QPalette(); app = QApplication.instance()
        for role, key in ((QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.WindowText, "text"), (QPalette.ColorRole.Base, "surface"), (QPalette.ColorRole.AlternateBase, "panel"),
                          (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "surface"), (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "accent"),
                          (QPalette.ColorRole.HighlightedText, "onacc"), (QPalette.ColorRole.ToolTipBase, "surface"), (QPalette.ColorRole.ToolTipText, "text"), (QPalette.ColorRole.PlaceholderText, "muted")):
            pal.setColor(role, QColor(PAL[key]))
        app.setPalette(pal)
        self.refresh_items()
    def set_opts(self, o):
        was = OPT["thumbs"]; OPT.clear(); OPT.update(DEFAULTS); OPT.update(o); self.cfg.setValue("opt2", json.dumps(OPT))
        self.apply_opts(); self.layout_side()
        if OPT["thumbs"] and not was and self.yt_ids: threading.Thread(target=self.yt_thumbs, args=(list(dict.fromkeys(self.yt_ids)),), daemon=True).start()
    def clear_zips(self):
        if QMessageBox.question(self, "Clear extracted zips", "Delete the extracted copies of zip files? Your original zips aren't touched.") == QMessageBox.StandardButton.Yes:
            shutil.rmtree(Path.home() / ".playlistplayer" / "zips", ignore_errors=True)
    def open_settings(self):
        o = dict(OPT); d = QDialog(self); d.setWindowTitle("Appearance & settings"); d.setMinimumWidth(560)
        lay = QVBoxLayout(d); lay.setContentsMargins(26, 24, 26, 20); lay.setSpacing(14)
        h = QLabel("Customise"); h.setObjectName("head"); lay.addWidget(h)
        form = QFormLayout(); form.setSpacing(12); form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft); lay.addLayout(form)
        paints = []; preset = QComboBox(); preset.addItems(list(PRESETS) + ["Custom"]); preset.setCurrentText(o.get("preset", "Custom"))
        def colour(key):
            b = QPushButton(); b.setMinimumHeight(34)
            def paint():
                b.setText(o[key].upper()); b.setStyleSheet(f"background:{o[key]};color:{'#fff' if QColor(o[key]).lightnessF() < .5 else '#000'};border:1px solid #888;border-radius:8px")
            def pick():
                c = QColorDialog.getColor(QColor(o[key]), d, "Choose colour")
                if c.isValid():
                    o[key] = c.name(); paint(); preset.blockSignals(True); preset.setCurrentText("Custom"); preset.blockSignals(False)
            b.clicked.connect(pick); paint(); paints.append(paint); return b
        def choose(name):
            if name in PRESETS:
                o.update(PRESETS[name])
                for p in paints: p()
        preset.currentTextChanged.connect(choose)
        font = QFontComboBox(); font.setCurrentFont(QFont(o["font"]))
        size = QSpinBox(); size.setRange(10, 20); size.setValue(int(o["size"])); size.setSuffix(" px")
        rad = QSpinBox(); rad.setRange(0, 16); rad.setValue(int(o["radius"])); rad.setSuffix(" px")
        side = QComboBox(); side.addItems(["Right", "Left"]); side.setCurrentText(str(o["side"]).title())
        step = QSpinBox(); step.setRange(1, 60); step.setValue(int(o["step"])); step.setSuffix(" s")
        mop = QSpinBox(); mop.setRange(40, 100); mop.setValue(int(o["mini_opacity"])); mop.setSuffix(" %")
        thumbs = QCheckBox("Show video thumbnails"); thumbs.setChecked(bool(o["thumbs"]))
        resume = QCheckBox("Remember video progress and resume where I left off"); resume.setChecked(bool(o["resume"]))
        form.addRow("Theme", preset); form.addRow("Accent colour", colour("accent")); form.addRow("Background", colour("bg")); form.addRow("Text colour", colour("text"))
        form.addRow("Font", font); form.addRow("Font size", size); form.addRow("Roundness", rad); form.addRow("Playlist side", side)
        form.addRow("Arrow-key skip", step); form.addRow("Mini player opacity", mop); form.addRow("", thumbs); form.addRow("", resume)
        row = QHBoxLayout(); reset = QPushButton("Reset to defaults"); cancel = QPushButton("Cancel"); ok = QPushButton("Apply"); ok.setObjectName("primary"); ok.setDefault(True)
        row.addWidget(reset); row.addStretch(1); row.addWidget(cancel); row.addWidget(ok); lay.addSpacing(6); lay.addLayout(row)
        def done():
            o.update(font=font.currentFont().family(), size=size.value(), radius=rad.value(), side=side.currentText().lower(), step=step.value(),
                     mini_opacity=mop.value(), thumbs=thumbs.isChecked(), resume=resume.isChecked(), preset=preset.currentText())
            self.set_opts(o); d.accept()
        def rst(): self.set_opts(dict(DEFAULTS)); d.reject()
        ok.clicked.connect(done); cancel.clicked.connect(d.reject); reset.clicked.connect(rst); d.exec()

    # ---- mini player + fullscreen state
    def on_dur(self, d):
        if d > 0 and 0 <= self.idx < len(self.files) and not self.ytb.isChecked(): self.durs[self.files[self.idx]] = d; self.refresh_items()
    def yt_plmeta(self, pid):
        try:
            j = json.load(urllib.request.urlopen(urllib.request.Request("https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/playlist?list=" + pid, headers={"User-Agent": "Mozilla/5.0"}), timeout=10))
            self.title_found.emit("PL:" + pid, j.get("title", ""), j.get("author_name", ""))
        except Exception: pass
    def on_state(self, s):
        t = "⏸" if s == QMediaPlayer.PlaybackState.PlayingState else "▶"; self.pbtn.setText(t)
        self.fsw.pb.setText(t)
        if not self.ytb.isChecked(): self.mini.pb.setText(t)
    def mini_play(self):
        if self.ytb.isChecked(): self.yt_cmd("p.getPlayerState()==1?p.pauseVideo():p.playVideo()")
        else: self.toggle()
    def mini_toggle(self):
        m = self.mini
        if m.isVisible():                      # back to the full player
            w = m.surface; m.lay.removeWidget(w); self.stack.addWidget(w); self.stack.setCurrentWidget(w)
            self.cfg.setValue("mini_geo2", m.saveGeometry()); m.surface = None; m.hide()
            self.showNormal(); self.raise_(); self.activateWindow()
        else:                                  # shrink into the mini player
            if self.fsw.isVisible(): self.exit_fs()
            yt = self.ytb.isChecked(); w = self.web if yt else self.video
            self.stack.removeWidget(w); m.lay.insertWidget(0, w, 1); w.show(); m.surface = w
            m.seek.setVisible(not yt); m.pb.setText("⏯" if yt else self.pbtn.text())
            g = self.cfg.value("mini_geo2")
            if g: m.restoreGeometry(g)
            else: m.resize(380, 232)
            m.show(); m.raise_(); m.activateWindow(); self.showMinimized()
    def yt_fs(self, r):
        if self.mini.isVisible(): r.reject(); return
        r.accept()
        if r.toggleOn():
            if not self.fsw.isVisible(): self.fs_page = True; self.enter_fs()
        elif getattr(self, "fs_page", False): self.exit_fs()
    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange and hasattr(self, "mini") and hasattr(self, "strip"):
            if self.mini.isVisible():
                if not self.isMinimized(): QTimer.singleShot(0, self.mini_toggle)   # restored from taskbar -> bring video back
            elif self.isFullScreen() != self._was_fs:
                self._was_fs = self.isFullScreen(); self.fs_ui(self._was_fs)       # sidebar + stats follow ANY fullscreen
        super().changeEvent(e)

    # ---- updater (GitHub Releases)
    def update_repo(self): return (self.cfg.value("update_repo", "") or UPDATE_REPO).strip()
    def set_update_repo(self):
        t = self.ask("Update source", "The GitHub repository that hosts your releases, written as owner/name (for example yourname/playlist-player). It must be public.", self.update_repo(), None, "owner/name")
        if t is None: return False
        t = re.sub(r"^https?://github\.com/", "", t).strip("/ ")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", t): QMessageBox.warning(self, "Updates", "That doesn't look like owner/name."); return False
        self.cfg.setValue("update_repo", t); return True
    def check_update(self, manual=False):
        repo = self.update_repo()
        if not repo:
            if not manual or not self.set_update_repo(): return
            repo = self.update_repo()
        def work():
            try:
                rq = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest", headers={"User-Agent": "PlaylistPlayer", "Accept": "application/vnd.github+json"})
                d = json.load(urllib.request.urlopen(rq, timeout=15)); tag = d.get("tag_name", "")
                m = re.search(r"\d+(?:\.\d+)*", tag)
                if not m: raise RuntimeError(f"The latest release is tagged '{tag}', which has no version number.")
                newer = tuple(map(int, m.group(0).split("."))) > tuple(map(int, __version__.split(".")))
                exes = [a for a in d.get("assets", []) if a["name"].lower().endswith(".exe")]
                a = next((x for x in exes if "setup" in x["name"].lower()), exes[0] if exes else None)
                if newer and not a: raise RuntimeError(f"Release {tag} has no installer (.exe) attached.")
                self.update_found.emit(m.group(0) if newer else "", a["browser_download_url"] if newer else ("manual" if manual else ""))
            except urllib.error.HTTPError as e:
                msg = {404: f"No published release found in {repo}. The repository must be public and have a release with the installer attached.",
                       403: "GitHub is rate-limiting this PC. Try again in a few minutes."}.get(e.code, f"GitHub returned error {e.code}.")
                if manual: self.update_found.emit("", "error:" + msg)
            except Exception as e:
                if manual: self.update_found.emit("", "error:" + (str(e) if isinstance(e, RuntimeError) else "Couldn't reach GitHub. Check your internet connection."))
        threading.Thread(target=work, daemon=True).start()
    def on_update(self, tag, url):
        if url.startswith("error:"): QMessageBox.warning(self, "Updates", url[6:]); return
        if not tag:
            if url == "manual": QMessageBox.information(self, "Updates", f"You're up to date (v{__version__}).")
            return
        if QMessageBox.question(self, "Update available", f"Version {tag} is available (you have v{__version__}).\n\nDownload and install it now? The app will close and reopen by itself.") != QMessageBox.StandardButton.Yes: return
        self.dlg = QProgressDialog("Downloading update…", None, 0, 100, self); self.dlg.setWindowTitle("Updating Playlist Player")
        self.dlg.setWindowModality(Qt.WindowModality.WindowModal); self.dlg.setMinimumDuration(0); self.dlg.setValue(0)
        dest = os.path.join(tempfile.gettempdir(), "PlaylistPlayer-Setup.exe")
        def work():
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "PlaylistPlayer"}), timeout=30) as r, open(dest, "wb") as f:
                    total = int(r.headers.get("Content-Length") or 0); got = 0
                    while True:
                        b = r.read(1 << 16)
                        if not b: break
                        f.write(b); got += len(b)
                        if total: self.dl_progress.emit(int(got * 100 / total))
                self.dl_done.emit(dest)
            except Exception: self.dl_done.emit("")
        threading.Thread(target=work, daemon=True).start()
    def on_dl_progress(self, p):
        if getattr(self, "dlg", None): self.dlg.setValue(p)
    def on_dl_done(self, path):
        if getattr(self, "dlg", None): self.dlg.close(); self.dlg = None
        if not path: QMessageBox.warning(self, "Updates", "The download failed. Please try again."); return
        self.save()
        subprocess.Popen([path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        QApplication.quit()

    # ---- UI
    def flash(self, t):
        self.osd.setText(t); self.osd.adjustSize(); self.osd.move(20, 20); self.osd.show(); self.osd_t.start()
    def toggle_side(self): self.side.setVisible(not self.side.isVisible())
    def fullscreen(self):
        if self.fsw.isVisible(): self.exit_fs()
        else: self.enter_fs()
    def enter_fs(self):
        if self.fsw.isVisible() or self.mini.isVisible(): return
        f = self.fsw; yt = self.ytb.isChecked(); w = self.web if yt else self.video
        self.stack.removeWidget(w); f.lay.insertWidget(0, w, 1); w.show(); f.surface = w; f.local = not yt
        f.bar.hide(); f.seek.setRange(0, self.mp.duration()); f.pb.setText(self.pbtn.text())
        f.showFullScreen(); f.raise_(); f.activateWindow(); self.hide()
    def exit_fs(self):
        f = self.fsw
        if not f.isVisible(): return
        w = f.surface; f.lay.removeWidget(w); self.stack.addWidget(w); self.stack.setCurrentWidget(w); f.surface = None
        self.fs_page = False; self.show(); self.raise_(); self.activateWindow(); f.hide()
    def fs_ui(self, on): pass
    def autohide(self):
        if self.isFullScreen(): self.controls.hide(); self.setCursor(Qt.CursorShape.BlankCursor)
    def eventFilter(self, o, e):
        if e.type() == QEvent.Type.MouseMove and self.isFullScreen():
            self.controls.setVisible(not self.ytb.isChecked()); self.unsetCursor(); self.hide_t.start()
        if o is self.video:
            if e.type() == QEvent.Type.MouseButtonRelease: self.toggle()
            if e.type() == QEvent.Type.MouseButtonDblClick: self.fullscreen()
        return False
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self, e): self.load_path(e.mimeData().urls()[0].toLocalFile())
    def wheelEvent(self, e): self.volstep(5 if e.angleDelta().y() > 0 else -5)

    def save(self):
        self.cfg.setValue("positions", json.dumps(self.pos)); self.cfg.setValue("watched", json.dumps(list(self.watched)))
        self.cfg.setValue("volume", self.audio.volume())
        self.cfg.setValue("yt_watched", json.dumps(list(self.yt_watched))); self.cfg.setValue("yt_titles", json.dumps(self.yt_titles)); self.cfg.setValue("yt_stats", json.dumps(dict(self.yt_stats)))
        self.cfg.setValue("yt_pos", json.dumps(dict(self.yt_pos))); self.cfg.setValue("yt_time", self.yt_last_t)
        self.cfg.setValue("mode", "yt" if self.ytb.isChecked() else "local"); self.cfg.setValue("durs", json.dumps(dict(self.durs)))
    def cleanup(self):
        if self.tmp: self.mp.setSource(QUrl()); shutil.rmtree(self.tmp, ignore_errors=True); self.tmp = None
    def closeEvent(self, e):
        if self.mini.isVisible(): self.mini_toggle()
        if self.fsw.isVisible(): self.exit_fs()
        self.save(); self.cfg.setValue("geometry", self.saveGeometry()); self.cleanup(); super().closeEvent(e)

if __name__ == "__main__":
    sys.excepthook = _excepthook; app = QApplication(sys.argv); app.setStyle("Fusion"); OPT.update(json.loads(QSettings("PlaylistPlayer", "PlaylistPlayer").value("opt2", "{}"))); app.setStyleSheet(themed(STYLE))
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    app.setWindowIcon(QIcon(os.path.join(base, "icon.ico")))
    w = Player(); w.show(); sys.exit(app.exec())
