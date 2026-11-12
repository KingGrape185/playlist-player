import sys, os, re, json, random, zipfile, tempfile, shutil
from pathlib import Path
from PyQt6.QtCore import Qt, QUrl, QTimer, QSettings, QEvent
from PyQt6.QtGui import QIcon, QShortcut, QKeySequence
from PyQt6.QtWidgets import *
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
import threading, subprocess, urllib.request, time
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
QWidget{background:#0f0f11;color:#e9e9ec;font-family:'Segoe UI',sans-serif;font-size:13px}
QLabel{background:transparent}
QSplitter::handle{background:#1b1b1f;width:1px}
QLabel#head{font-size:15px;font-weight:600;padding:2px}
QLabel#nowTitle{font-size:17px;font-weight:600}
QLabel#nowMeta{color:#9b9ba4;font-size:12px}
QWidget#strip,QWidget#controls{background:#131316}
QListWidget{background:transparent;border:none;outline:0}
QListWidget::item{padding:8px 10px;border-radius:8px;margin:1px 0;color:#c9c9cf}
QListWidget::item:hover{background:#1a1a1e}
QListWidget::item:selected{background:#2a1715;color:#ff7a6e}
QLineEdit{background:#18181c;border:1px solid #26262c;border-radius:8px;padding:7px 10px}
QLineEdit:focus{border-color:#ff4b3e}
QComboBox{background:#18181c;border:1px solid #26262c;border-radius:8px;padding:5px 8px}
QComboBox QAbstractItemView{background:#18181c;selection-background-color:#2a1715}
QPushButton{background:transparent;border:none;border-radius:8px;padding:7px 10px;color:#d8d8dc}
QPushButton:hover{background:#202025}
QPushButton:checked{background:#2a1715;color:#ff6a5c}
QSlider::groove:horizontal{height:4px;background:#2a2a30;border-radius:2px}
QSlider::sub-page:horizontal{background:#ff4b3e;border-radius:2px}
QSlider::handle:horizontal{background:#fff;width:12px;height:12px;margin:-4px 0;border-radius:6px}
QScrollBar:vertical{background:transparent;width:8px}
QScrollBar::handle:vertical{background:#2a2a30;border-radius:4px;min-height:30px}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
"""

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

class Mini(QWidget):
    """Small always-on-top window. The video (or YouTube view) is moved in here, so playback never restarts."""
    def __init__(self, o):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.o = o; self.surface = None
        self.setWindowTitle("Mini player"); self.setWindowIcon(o.windowIcon()); self.setMinimumSize(300, 220)
        self.lay = QVBoxLayout(self); self.lay.setContentsMargins(0, 0, 0, 0); self.lay.setSpacing(0)
        def b(t, tip, f):
            x = QPushButton(t); x.setToolTip(tip); x.clicked.connect(f); x.setFocusPolicy(Qt.FocusPolicy.NoFocus); x.setMinimumWidth(34); return x
        self.pb = b("▶", "Play / pause (Space)", o.mini_play)
        self.seek = ClickSlider(Qt.Orientation.Horizontal); self.seek.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.seek.sliderMoved.connect(o.mp.setPosition)
        bar = QWidget(); bar.setObjectName("controls"); h = QHBoxLayout(bar); h.setContentsMargins(8, 4, 8, 6); h.setSpacing(2)
        for w in (b("⏮", "Previous", o.prev), self.pb, b("⏭", "Next", o.next)): h.addWidget(w)
        h.addWidget(self.seek, 100); h.addStretch(1); h.addWidget(b("⤢", "Back to full player (I / Esc)", o.mini_toggle))
        self.lay.addWidget(bar)
        for k, f in {"Space": o.mini_play, "I": o.mini_toggle, "Esc": o.mini_toggle, "Left": lambda: o.skip(-5), "Right": lambda: o.skip(5)}.items():
            QShortcut(QKeySequence(k), self, activated=f)
    def closeEvent(self, e):
        e.ignore(); self.o.mini_toggle()

class Player(QMainWindow):
    update_found = pyqtSignal(str, str)
    title_found = pyqtSignal(str, str, str)
    stats_found = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Playlist Player"); self.setAcceptDrops(True)
        self.cfg = QSettings("PlaylistPlayer", "PlaylistPlayer")
        self.tmp = None; self.files = []; self.idx = -1; self.order = []
        self.pos = json.loads(self.cfg.value("positions", "{}")); self.watched = set(json.loads(self.cfg.value("watched", "[]")))
        self.repeat = 0
        self.yt_watched = set(json.loads(self.cfg.value("yt_watched", "[]"))); self.yt_titles = json.loads(self.cfg.value("yt_titles", "{}")); self.yt_stats = json.loads(self.cfg.value("yt_stats", "{}"))
        self.yt_ids = []; self.yt_cur = -1; self.yt_pid = ""; self._was_fs = False; self.yt_failed = set()
        self.yt_timer = QTimer(interval=1000); self.yt_timer.timeout.connect(self.yt_poll)
        self.audio = QAudioOutput(); self.mp = QMediaPlayer(); self.mp.setAudioOutput(self.audio)
        self.audio.setVolume(float(self.cfg.value("volume", 0.8)))
        self.video = QVideoWidget(); self.mp.setVideoOutput(self.video)
        self.video.installEventFilter(self)
        self.mini = Mini(self)

        # sidebar
        self.search = QLineEdit(); self.search.setPlaceholderText("Search playlist…"); self.search.textChanged.connect(self.filter)
        self.list = QListWidget(); self.list.itemDoubleClicked.connect(lambda it: self.play(it.data(Qt.ItemDataRole.UserRole)))
        self.info = QLabel("Drop a folder or .zip here"); self.info.setWordWrap(True)
        openb = QPushButton("Open folder"); openb.clicked.connect(self.open_folder)
        zipb = QPushButton("Open zip"); zipb.clicked.connect(self.open_zip)
        self.ytb = QPushButton("▶ YouTube mode (counts views)"); self.ytb.setCheckable(True); self.ytb.clicked.connect(self.yt_toggle)
        minib = QPushButton("◱  Mini player (I)"); minib.clicked.connect(self.mini_toggle)
        keyb = QPushButton("YouTube API key…"); keyb.setToolTip("Optional: reliable views / upload dates"); keyb.clicked.connect(self.set_key)
        updb = QPushButton(f"Check for updates (v{__version__})"); updb.clicked.connect(lambda: self.check_update(True))
        row = QHBoxLayout(); row.addWidget(openb); row.addWidget(zipb)
        side = QWidget(); sl = QVBoxLayout(side); sl.setContentsMargins(12, 12, 12, 12); sl.setSpacing(8)
        self.ytlist = QListWidget(); self.ytlist.hide(); self.ytlist.itemDoubleClicked.connect(self.yt_play_item)
        self.head = QLabel("Local files"); self.head.setObjectName("head")
        for w in (self.head, self.search, self.list, self.ytlist, self.info): sl.addWidget(w)
        sl.addLayout(row); sl.addWidget(self.ytb); sl.addWidget(minib); sl.addWidget(keyb); sl.addWidget(updb); side.setMinimumWidth(260); self.side = side

        # controls
        def btn(t, tip, f, chk=False):
            b = QPushButton(t); b.setToolTip(tip); b.clicked.connect(f); b.setCheckable(chk); b.setFocusPolicy(Qt.FocusPolicy.NoFocus); b.setMinimumWidth(38); return b
        self.pbtn = btn("▶", "Play/Pause (Space)", self.toggle)
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
        self.osd = QLabel("", self.video); self.osd.setStyleSheet("background:rgba(0,0,0,170);padding:8px 14px;border-radius:8px;font-size:16px"); self.osd.hide()
        self.osd_t = QTimer(singleShot=True, interval=1200); self.osd_t.timeout.connect(self.osd.hide)

        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(0); self.stack = QStackedWidget(); self.stack.addWidget(self.video); self.web = None; ll.addWidget(self.stack, 1)
        self.strip = QWidget(); self.strip.setObjectName("strip"); sv = QVBoxLayout(self.strip); sv.setContentsMargins(16, 12, 16, 12); sv.setSpacing(2)
        self.now_title = QLabel(); self.now_title.setObjectName("nowTitle"); self.now_meta = QLabel(); self.now_meta.setObjectName("nowMeta")
        sv.addWidget(self.now_title); sv.addWidget(self.now_meta); self.show_local()
        ll.addWidget(self.strip); ll.addWidget(self.controls)
        sp = QSplitter(); sp.addWidget(left); sp.addWidget(side); sp.setStretchFactor(0, 1); sp.setSizes([980, 300]); self.setCentralWidget(sp)
        self.sp = sp

        self.mp.positionChanged.connect(self.on_pos); self.mp.durationChanged.connect(lambda d: (self.seek.setRange(0, d), self.mini.seek.setRange(0, d)))
        self.mp.playbackStateChanged.connect(self.on_state)
        self.mp.mediaStatusChanged.connect(self.on_status); self.mp.errorOccurred.connect(self.on_error)
        self.hide_t = QTimer(singleShot=True, interval=2500); self.hide_t.timeout.connect(self.autohide)
        QApplication.instance().installEventFilter(self)
        self.save_t = QTimer(interval=5000); self.save_t.timeout.connect(self.save); self.save_t.start()

        for k, f in {"Space": self.toggle, "K": self.toggle, "Left": lambda: self.skip(-5), "Right": lambda: self.skip(5), "J": lambda: self.skip(-10),
                     "L": lambda: self.skip(10), "Up": lambda: self.volstep(5), "Down": lambda: self.volstep(-5), "F": self.fullscreen, "Esc": self.exit_fs,
                     "N": self.next, "P": self.prev, "M": self.mute, "S": lambda: self.shuf.click(), "R": self.cycle_repeat, "T": self.toggle_side,
                     "]": lambda: self.step_speed(1), "[": lambda: self.step_speed(-1), "Ctrl+O": self.open_folder, "I": self.mini_toggle, "F11": self.fullscreen, "Ctrl+F": lambda: self.search.setFocus()}.items():
            QShortcut(QKeySequence(k), self, activated=f)
        for d in range(10): QShortcut(QKeySequence(str(d)), self, activated=lambda d=d: self.mp.setPosition(int(self.mp.duration() * d / 10)))
        g = self.cfg.value("geometry")
        if g: self.restoreGeometry(g)
        else: self.resize(1280, 760)
        self.update_found.connect(self.on_update); self.title_found.connect(self.on_title); self.stats_found.connect(self.on_stats); QTimer.singleShot(4000, self.check_update)
        last = self.cfg.value("source")
        if last and os.path.isdir(last): self.load_dir(last)
        elif len(sys.argv) > 1: self.load_path(sys.argv[1])

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
        self.cleanup(); self.tmp = tempfile.mkdtemp(prefix="plp_"); self.info.setText("Extracting…"); QApplication.processEvents()
        with zipfile.ZipFile(f) as z: z.extractall(self.tmp)
        self.load_dir(self.tmp, remember=False)
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
            it.setText(("✓ " if f in self.watched else "") + f"{i+1}. {Path(f).stem}")
    def filter(self, t):
        lst = self.ytlist if self.ytb.isChecked() else self.list
        for r in range(lst.count()): lst.item(r).setHidden(t.lower() not in lst.item(r).text().lower())
    def rebuild_order(self):
        self.order = list(range(len(self.files)))
        if self.shuf.isChecked(): random.shuffle(self.order)
        self.flash("Shuffle on" if self.shuf.isChecked() else "Shuffle off")

    # ---- playback
    def play(self, i, autostart=True):
        if not (0 <= i < len(self.files)): return
        self.idx = i; f = self.files[i]; self.cfg.setValue("last_file", f)
        self.mp.setSource(QUrl.fromLocalFile(f)); self.mp.setPlaybackRate(SPEEDS[self.speed.currentIndex()])
        self._resume = self.pos.get(f, 0)
        self.list.setCurrentRow(i); self.setWindowTitle(f"{Path(f).stem} — Playlist Player"); self.show_local()
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
        t, ok = QInputDialog.getText(self, "YouTube playlist", "Playlist URL or ID:", text=self.cfg.value("yt_pl", YT_PLAYLIST))
        t = t.strip() if ok else ""
        m = re.search(r"list=([\w-]+)", t); pid = m.group(1) if m else (t if re.fullmatch(r"[\w-]+", t) else None)
        if not pid: self.ytb.setChecked(False); return
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

    # ---- YouTube playlist sidebar (playback stays in YouTube's official player)
    PAGE = """<html><head><style>html,body,#p{margin:0;height:100%;background:#000}</style></head><body><div id="p"></div>
<script src="https://www.youtube.com/iframe_api"></script>
<script>
var p;
function onYouTubeIframeAPIReady(){
  p=new YT.Player('p',{width:'100%',height:'100%',playerVars:{autoplay:1,rel:0},
    events:{onReady:function(){p.loadPlaylist({listType:'playlist',list:'__PID__',index:__START__});}}});
}
</script></body></html>"""
    def yt_start(self, pid):
        self.yt_pid = pid; self.yt_ids = []; self.yt_cur = -1
        start = int(self.cfg.value("yt_idx", 0)) if self.cfg.value("yt_idx_for") == pid else 0
        self.web.setHtml(self.PAGE.replace("__PID__", pid).replace("__START__", str(start)), QUrl("https://playlist-player.app/"))
        self.ytlist.clear(); self.list.hide(); self.ytlist.show(); self.search.clear(); self.info.setText("Loading playlist…"); self.head.setText("YouTube playlist")
        self.yt_timer.start()
    def yt_off(self):
        self.yt_timer.stop(); self.stack.setCurrentWidget(self.video); self.web.setHtml("")
        self.controls.show(); self.side.show(); self.ytlist.hide(); self.list.show(); self.search.clear(); self.setWindowTitle("Playlist Player"); self.head.setText("Local files"); self.show_local()
        self.info.setText(f"{self.idx+1} of {len(self.files)}" if self.files else "Drop a folder or .zip here")
    def yt_cmd(self, js):
        if self.web: self.web.page().runJavaScript(js)
    def yt_poll(self):
        if self.web: self.web.page().runJavaScript("(window.p&&p.getPlaylist&&p.getPlaylist())?JSON.stringify({ids:p.getPlaylist(),i:p.getPlaylistIndex(),s:p.getPlayerState()}):''", self.yt_got)
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
            threading.Thread(target=self.yt_crawl, args=(list(dict.fromkeys(ids)), self.cfg.value("yt_key", "")), daemon=True).start()
        i = d.get("i")
        if ids and i is not None and 0 <= i < len(ids):
            if d.get("s") == 0 and ids[i] not in self.yt_watched: self.yt_watched.add(ids[i]); self.yt_label(i)
            if i != self.yt_cur:
                self.yt_cur = i; self.ytlist.setCurrentRow(i); self.cfg.setValue("yt_idx", i); self.cfg.setValue("yt_idx_for", self.yt_pid)
                self.info.setText(f"{i+1} of {len(ids)} · {sum(x in self.yt_watched for x in ids)} watched")
                self.yt_show(ids[i]); threading.Thread(target=self.yt_stat_one, args=(ids[i], 3600, self.cfg.value("yt_key", "")), daemon=True).start()
    def yt_label(self, k):
        it = self.ytlist.item(k)
        if not it: return
        v = self.yt_ids[k]; st = self.yt_stats.get(v, {})
        sub = "  ·  ".join(x for x in (st.get("author"), f"{fmt_views(st['views'])} views" if "views" in st else "", ago(st["date"]) if st.get("date") else "") if x)
        it.setText(("✓ " if v in self.yt_watched else "") + f"{k+1}. " + self.yt_titles.get(v, "Loading…") + (f"\n{sub}" if sub else ""))
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
        bits = [st["author"]] if st.get("author") else []
        if "views" in st: bits.append(f"{fmt_views(st['views'])} views")
        if st.get("date"): bits.append(f"Uploaded {ago(st['date'])} ({st['date']})")
        if v in self.yt_failed and "views" not in st: bits.append("views & upload date unavailable (add an API key in the sidebar)")
        self.now_title.setText(t or "Loading…"); self.now_meta.setText("  ·  ".join(bits) or "Loading stats…")
        if t: self.setWindowTitle(f"{t} — Playlist Player")
    def show_local(self):
        if 0 <= self.idx < len(self.files):
            f = self.files[self.idx]; self.now_title.setText(Path(f).stem)
            self.now_meta.setText(f"Local file  ·  {os.path.getsize(f)/1e6:.0f} MB  ·  {self.idx+1} of {len(self.files)}")
        else: self.now_title.setText("Nothing playing"); self.now_meta.setText("Open a folder, or switch on YouTube mode")
    def set_key(self):
        t, ok = QInputDialog.getText(self, "YouTube API key", "Paste a YouTube Data API v3 key (empty = remove):", text=self.cfg.value("yt_key", ""))
        if not ok: return
        self.cfg.setValue("yt_key", t.strip()); self.yt_failed.clear()
        self.yt_stats = {k: {**x, "t": 0} for k, x in dict(self.yt_stats).items()}
        QMessageBox.information(self, "Saved", "Turn YouTube mode off and on again to refresh the stats.")
    def yt_api(self, ids, key):
        ok = False
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            try:
                u = "https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id=" + ",".join(chunk) + "&key=" + key
                for it in json.load(urllib.request.urlopen(u, timeout=15)).get("items", []):
                    v = it["id"]; sn = it["snippet"]; stt = it.get("statistics", {}); st = dict(self.yt_stats.get(v, {}))
                    st.update(author=sn.get("channelTitle", ""), date=sn.get("publishedAt", "")[:10], t=time.time())
                    if "viewCount" in stt: st["views"] = int(stt["viewCount"])
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

    # ---- mini player + fullscreen state
    def on_state(self, s):
        t = "⏸" if s == QMediaPlayer.PlaybackState.PlayingState else "▶"; self.pbtn.setText(t)
        if not self.ytb.isChecked(): self.mini.pb.setText(t)
    def mini_play(self):
        if self.ytb.isChecked(): self.yt_cmd("p.getPlayerState()==1?p.pauseVideo():p.playVideo()")
        else: self.toggle()
    def mini_toggle(self):
        m = self.mini
        if m.isVisible():                      # back to the full player
            w = m.surface; m.lay.removeWidget(w); self.stack.addWidget(w); self.stack.setCurrentWidget(w)
            self.cfg.setValue("mini_geo", m.saveGeometry()); m.surface = None; m.hide()
            self.showNormal(); self.raise_(); self.activateWindow()
        else:                                  # shrink into the mini player
            if self.isFullScreen(): self.exit_fs()
            yt = self.ytb.isChecked(); w = self.web if yt else self.video
            self.stack.removeWidget(w); m.lay.insertWidget(0, w, 1); w.show(); m.surface = w
            m.seek.setVisible(not yt); m.pb.setText("⏯" if yt else self.pbtn.text())
            g = self.cfg.value("mini_geo")
            if g: m.restoreGeometry(g)
            else: m.resize(440, 300)
            m.show(); m.raise_(); m.activateWindow(); self.showMinimized()
    def yt_fs(self, r):
        if self.mini.isVisible(): r.reject(); return
        r.accept(); self.enter_fs() if r.toggleOn() else self.exit_fs()
    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange and hasattr(self, "mini") and hasattr(self, "strip"):
            if self.mini.isVisible():
                if not self.isMinimized(): QTimer.singleShot(0, self.mini_toggle)   # restored from taskbar -> bring video back
            elif self.isFullScreen() != self._was_fs:
                self._was_fs = self.isFullScreen(); self.fs_ui(self._was_fs)       # sidebar + stats follow ANY fullscreen
        super().changeEvent(e)

    # ---- updater (GitHub Releases)
    def check_update(self, manual=False):
        if not UPDATE_REPO:
            if manual: QMessageBox.information(self, "Updates", "Set UPDATE_REPO in player.py to your GitHub owner/repo first.")
            return
        def work():
            try:
                rq = urllib.request.Request(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest", headers={"User-Agent": "PlaylistPlayer"})
                d = json.load(urllib.request.urlopen(rq, timeout=10))
                tag = d["tag_name"].lstrip("v")
                url = next(a["browser_download_url"] for a in d["assets"] if a["name"].lower().endswith("setup.exe"))
                newer = tuple(map(int, tag.split("."))) > tuple(map(int, __version__.split(".")))
                self.update_found.emit(tag if newer else "", url if newer else ("manual" if manual else ""))
            except Exception:
                if manual: self.update_found.emit("", "error")
        threading.Thread(target=work, daemon=True).start()
    def on_update(self, tag, url):
        if url == "error": QMessageBox.warning(self, "Updates", "Couldn't check for updates."); return
        if not tag:
            if url == "manual": QMessageBox.information(self, "Updates", f"You're up to date (v{__version__}).")
            return
        if QMessageBox.question(self, "Update available", f"Version {tag} is available. Install now?") != QMessageBox.StandardButton.Yes: return
        self.setCursor(Qt.CursorShape.WaitCursor); dest = os.path.join(tempfile.gettempdir(), "PlaylistPlayer-Setup.exe")
        try: urllib.request.urlretrieve(url, dest)
        except Exception: self.unsetCursor(); QMessageBox.warning(self, "Updates", "Download failed."); return
        subprocess.Popen([dest, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"]); QApplication.quit()

    # ---- UI
    def flash(self, t):
        self.osd.setText(t); self.osd.adjustSize(); self.osd.move(20, 20); self.osd.show(); self.osd_t.start()
    def toggle_side(self): self.side.setVisible(not self.side.isVisible())
    def fullscreen(self):
        if self.mini.isVisible(): return
        if self.isFullScreen(): self.exit_fs()
        else:
            self.enter_fs()
    def enter_fs(self):
        self._was_fs = True; self.showFullScreen(); self.fs_ui(True); self.hide_t.start()
    def fs_ui(self, on):
        self.side.setVisible(not on); self.strip.setVisible(not on); self.controls.setVisible(not self.ytb.isChecked())
    def exit_fs(self):
        if self.isFullScreen(): self._was_fs = False; self.showNormal(); self.fs_ui(False); self.unsetCursor()
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
    def cleanup(self):
        if self.tmp: self.mp.setSource(QUrl()); shutil.rmtree(self.tmp, ignore_errors=True); self.tmp = None
    def closeEvent(self, e):
        if self.mini.isVisible(): self.mini_toggle()
        if self.isFullScreen(): self.showNormal()
        self.save(); self.cfg.setValue("geometry", self.saveGeometry()); self.cleanup(); super().closeEvent(e)

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyleSheet(STYLE)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    app.setWindowIcon(QIcon(os.path.join(base, "icon.ico")))
    w = Player(); w.show(); sys.exit(app.exec())
