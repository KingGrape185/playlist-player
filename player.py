import sys, os, re, json, random, zipfile, tempfile, shutil
from pathlib import Path
from PyQt6.QtCore import Qt, QUrl, QTimer, QSettings, QEvent
from PyQt6.QtGui import QIcon, QShortcut, QKeySequence
from PyQt6.QtWidgets import *
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
import threading, subprocess, urllib.request
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
QWidget{background:#121214;color:#e8e8ea;font-size:13px}
QListWidget{background:#18181b;border:none;outline:0}
QListWidget::item{padding:7px 8px;border-bottom:1px solid #202024}
QListWidget::item:selected{background:#3a1c1a;color:#ff6a5c}
QLineEdit,QComboBox{background:#202024;border:1px solid #2c2c32;border-radius:6px;padding:4px 6px}
QPushButton{background:#202024;border:none;border-radius:6px;padding:6px 10px}
QPushButton:hover{background:#2c2c32} QPushButton:checked{background:#ff4b3e;color:white}
QSlider::groove:horizontal{height:5px;background:#2c2c32;border-radius:2px}
QSlider::sub-page:horizontal{background:#ff4b3e;border-radius:2px}
QSlider::handle:horizontal{background:#ff6a5c;width:12px;margin:-4px 0;border-radius:6px}
"""

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

class Player(QMainWindow):
    update_found = pyqtSignal(str, str)
    title_found = pyqtSignal(str, str)
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Playlist Player"); self.setAcceptDrops(True)
        self.cfg = QSettings("PlaylistPlayer", "PlaylistPlayer")
        self.tmp = None; self.files = []; self.idx = -1; self.order = []
        self.pos = json.loads(self.cfg.value("positions", "{}")); self.watched = set(json.loads(self.cfg.value("watched", "[]")))
        self.repeat = 0
        self.yt_watched = set(json.loads(self.cfg.value("yt_watched", "[]"))); self.yt_titles = json.loads(self.cfg.value("yt_titles", "{}"))
        self.yt_ids = []; self.yt_cur = -1; self.yt_pid = ""
        self.yt_timer = QTimer(interval=1000); self.yt_timer.timeout.connect(self.yt_poll)
        self.audio = QAudioOutput(); self.mp = QMediaPlayer(); self.mp.setAudioOutput(self.audio)
        self.audio.setVolume(float(self.cfg.value("volume", 0.8)))
        self.video = QVideoWidget(); self.mp.setVideoOutput(self.video)
        self.video.installEventFilter(self)

        # sidebar
        self.search = QLineEdit(); self.search.setPlaceholderText("Search playlist…"); self.search.textChanged.connect(self.filter)
        self.list = QListWidget(); self.list.itemDoubleClicked.connect(lambda it: self.play(it.data(Qt.ItemDataRole.UserRole)))
        self.info = QLabel("Drop a folder or .zip here"); self.info.setWordWrap(True)
        openb = QPushButton("Open folder"); openb.clicked.connect(self.open_folder)
        zipb = QPushButton("Open zip"); zipb.clicked.connect(self.open_zip)
        self.ytb = QPushButton("▶ YouTube mode (counts views)"); self.ytb.setCheckable(True); self.ytb.clicked.connect(self.yt_toggle)
        updb = QPushButton("Check for updates"); updb.clicked.connect(lambda: self.check_update(True))
        row = QHBoxLayout(); row.addWidget(openb); row.addWidget(zipb)
        side = QWidget(); sl = QVBoxLayout(side); sl.setContentsMargins(6, 6, 6, 6)
        self.ytlist = QListWidget(); self.ytlist.hide(); self.ytlist.itemDoubleClicked.connect(self.yt_play_item)
        for w in (self.search, self.list, self.ytlist, self.info): sl.addWidget(w)
        sl.addLayout(row); sl.addWidget(self.ytb); sl.addWidget(updb); side.setMinimumWidth(260); self.side = side

        # controls
        def btn(t, tip, f, chk=False):
            b = QPushButton(t); b.setToolTip(tip); b.clicked.connect(f); b.setCheckable(chk); b.setFocusPolicy(Qt.FocusPolicy.NoFocus); return b
        self.pbtn = btn("▶", "Play/Pause (Space)", self.toggle)
        self.seek = ClickSlider(Qt.Orientation.Horizontal); self.seek.sliderMoved.connect(self.mp.setPosition); self.seek.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.time = QLabel("0:00 / 0:00")
        self.speed = QComboBox(); self.speed.addItems([f"{s}x" for s in SPEEDS]); self.speed.setCurrentIndex(SPEEDS.index(float(self.cfg.value("speed", 1.0))))
        self.speed.currentIndexChanged.connect(self.set_speed); self.speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol = QSlider(Qt.Orientation.Horizontal); self.vol.setRange(0, 100); self.vol.setFixedWidth(90); self.vol.setValue(int(self.audio.volume() * 100))
        self.vol.valueChanged.connect(lambda v: self.audio.setVolume(v / 100)); self.vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.shuf = btn("🔀", "Shuffle (S)", self.rebuild_order, True)
        self.rep = btn("🔁", "Repeat: off (R)", self.cycle_repeat)
        self.auto = btn("Auto-next", "Play next video automatically", lambda: None, True); self.auto.setChecked(True)
        self.sleep = btn("💤", "Sleep timer: click to cycle off/15/30/60 min", self.cycle_sleep)
        self.sleep_min = 0; self.sleep_timer = QTimer(singleShot=True); self.sleep_timer.timeout.connect(lambda: (self.mp.pause(), self.flash("Sleep timer: paused")))
        bar = QHBoxLayout()
        for w in (btn("⏮", "Previous (P)", self.prev), self.pbtn, btn("⏭", "Next (N)", self.next), self.seek, self.time, self.speed,
                  btn("🔊", "Mute (M)", self.mute), self.vol, self.shuf, self.rep, self.auto, self.sleep,
                  btn("☰", "Toggle playlist (T)", self.toggle_side), btn("⛶", "Fullscreen (F)", self.fullscreen)):
            bar.addWidget(w, 1 if w is self.seek else 0)
        self.controls = QWidget(); self.controls.setLayout(bar)
        self.osd = QLabel("", self.video); self.osd.setStyleSheet("background:rgba(0,0,0,170);padding:8px 14px;border-radius:8px;font-size:16px"); self.osd.hide()
        self.osd_t = QTimer(singleShot=True, interval=1200); self.osd_t.timeout.connect(self.osd.hide)

        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(0); self.stack = QStackedWidget(); self.stack.addWidget(self.video); self.web = None; ll.addWidget(self.stack, 1); ll.addWidget(self.controls)
        sp = QSplitter(); sp.addWidget(left); sp.addWidget(side); sp.setStretchFactor(0, 1); sp.setSizes([980, 300]); self.setCentralWidget(sp)
        self.sp = sp

        self.mp.positionChanged.connect(self.on_pos); self.mp.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.mp.playbackStateChanged.connect(lambda s: self.pbtn.setText("⏸" if s == QMediaPlayer.PlaybackState.PlayingState else "▶"))
        self.mp.mediaStatusChanged.connect(self.on_status); self.mp.errorOccurred.connect(self.on_error)
        self.hide_t = QTimer(singleShot=True, interval=2500); self.hide_t.timeout.connect(self.autohide)
        QApplication.instance().installEventFilter(self)
        self.save_t = QTimer(interval=5000); self.save_t.timeout.connect(self.save); self.save_t.start()

        for k, f in {"Space": self.toggle, "K": self.toggle, "Left": lambda: self.skip(-5), "Right": lambda: self.skip(5), "J": lambda: self.skip(-10),
                     "L": lambda: self.skip(10), "Up": lambda: self.volstep(5), "Down": lambda: self.volstep(-5), "F": self.fullscreen, "Esc": self.exit_fs,
                     "N": self.next, "P": self.prev, "M": self.mute, "S": lambda: self.shuf.click(), "R": self.cycle_repeat, "T": self.toggle_side,
                     "]": lambda: self.step_speed(1), "[": lambda: self.step_speed(-1), "Ctrl+O": self.open_folder, "Ctrl+F": lambda: self.search.setFocus()}.items():
            QShortcut(QKeySequence(k), self, activated=f)
        for d in range(10): QShortcut(QKeySequence(str(d)), self, activated=lambda d=d: self.mp.setPosition(int(self.mp.duration() * d / 10)))
        g = self.cfg.value("geometry")
        if g: self.restoreGeometry(g)
        else: self.resize(1280, 760)
        self.update_found.connect(self.on_update); self.title_found.connect(self.on_title); QTimer.singleShot(4000, self.check_update)
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
        self.list.setCurrentRow(i); self.setWindowTitle(f"{Path(f).stem} — Playlist Player")
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
    def skip(self, s): self.mp.setPosition(max(0, self.mp.position() + s * 1000)); self.flash(f"{'+' if s > 0 else ''}{s}s")
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
            page.fullScreenRequested.connect(lambda r: (r.accept(), self.showFullScreen() if r.toggleOn() else self.showNormal()))
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
        self.ytlist.clear(); self.list.hide(); self.ytlist.show(); self.search.clear(); self.info.setText("Loading playlist…")
        self.yt_timer.start()
    def yt_off(self):
        self.yt_timer.stop(); self.stack.setCurrentWidget(self.video); self.web.setHtml("")
        self.controls.show(); self.side.show(); self.ytlist.hide(); self.list.show(); self.search.clear(); self.setWindowTitle("Playlist Player")
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
        i = d.get("i")
        if ids and i is not None and 0 <= i < len(ids):
            if d.get("s") == 0 and ids[i] not in self.yt_watched: self.yt_watched.add(ids[i]); self.yt_label(i)
            if i != self.yt_cur:
                self.yt_cur = i; self.ytlist.setCurrentRow(i); self.cfg.setValue("yt_idx", i); self.cfg.setValue("yt_idx_for", self.yt_pid)
                self.info.setText(f"{i+1} of {len(ids)} · {sum(x in self.yt_watched for x in ids)} watched")
    def yt_label(self, k):
        it = self.ytlist.item(k)
        if it: v = self.yt_ids[k]; it.setText(("✓ " if v in self.yt_watched else "") + f"{k+1}. " + self.yt_titles.get(v, "Loading…"))
    def yt_fetch_titles(self, ids):
        from concurrent.futures import ThreadPoolExecutor
        def one(v):
            try:
                u = "https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v=" + v
                return v, json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10))["title"]
            except Exception: return v, ""
        with ThreadPoolExecutor(8) as ex:
            for v, t in ex.map(one, ids): self.title_found.emit(v, t)
    def on_title(self, v, t):
        self.yt_titles[v] = t or "Unavailable video"
        for k, x in enumerate(self.yt_ids):
            if x == v: self.yt_label(k)
    def yt_play_item(self, it): self.yt_cmd(f"p.playVideoAt({self.ytlist.row(it)})")

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
        if self.isFullScreen(): self.exit_fs()
        else:
            self.showFullScreen(); self.side.hide(); self.hide_t.start()
    def exit_fs(self):
        if self.isFullScreen(): self.showNormal(); self.side.show(); self.controls.setVisible(not self.ytb.isChecked()); self.unsetCursor()
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
        self.cfg.setValue("yt_watched", json.dumps(list(self.yt_watched))); self.cfg.setValue("yt_titles", json.dumps(self.yt_titles))
    def cleanup(self):
        if self.tmp: self.mp.setSource(QUrl()); shutil.rmtree(self.tmp, ignore_errors=True); self.tmp = None
    def closeEvent(self, e):
        self.save(); self.cfg.setValue("geometry", self.saveGeometry()); self.cleanup(); super().closeEvent(e)

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyleSheet(STYLE)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    app.setWindowIcon(QIcon(os.path.join(base, "icon.ico")))
    w = Player(); w.show(); sys.exit(app.exec())
