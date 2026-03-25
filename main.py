# fullhd_glass_downloader.py
# Requires: pip install PySide6 yt-dlp
# Run: python fullhd_glass_downloader.py

import sys, os
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
import yt_dlp

def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def sizeof_fmt(num, suffix='B'):
    if not num:
        return ''
    for unit in ['','K','M','G','T','P']:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}P{suffix}"

class WorkerSignals(QtCore.QObject):
    progress = QtCore.Signal(float)
    status = QtCore.Signal(str)
    formats_ready = QtCore.Signal(list, dict)
    finished = QtCore.Signal(str)
    error = QtCore.Signal(str)

class FetchFormatsWorker(QtCore.QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = WorkerSignals()

    def run(self):
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            formats = info.get('formats', [])
            formats = [f for f in formats if f.get('ext')]
            # sort by resolution + bitrate
            formats.sort(key=lambda f: (f.get('height') or 0, f.get('tbr') or 0), reverse=True)
            # filter formats only up to native resolution
            max_height = max(f.get('height') or 0 for f in formats)
            formats = [f for f in formats if (f.get('height') or 0) <= max_height]
            self.signals.formats_ready.emit(formats, info)
            self.signals.status.emit("Formats fetched")
        except Exception as e:
            self.signals.error.emit(str(e))

class DownloadWorker(QtCore.QRunnable):
    def __init__(self, url, format_id, out_folder, ffmpeg_folder):
        super().__init__()
        self.url = url
        self.format_id = format_id
        self.out_folder = out_folder
        self.ffmpeg_folder = ffmpeg_folder
        self.signals = WorkerSignals()

    def run(self):
        try:
            os.makedirs(self.out_folder, exist_ok=True)
            outtmpl = os.path.join(self.out_folder, '%(title)s.%(ext)s')
            format_spec = f"{self.format_id}+bestaudio/best" if self.format_id else "best"
            ydl_opts = {
                'format': format_spec,
                'outtmpl': outtmpl,
                'quiet': True,
                'merge_output_format': 'mp4',
            }

            # ffmpeg handling
            if self.ffmpeg_folder and os.path.exists(os.path.join(self.ffmpeg_folder, "ffmpeg.exe")):
                os.environ["PATH"] = self.ffmpeg_folder + os.pathsep + os.environ.get("PATH", "")
                ydl_opts['ffmpeg_location'] = self.ffmpeg_folder

            def progress_hook(d):
                try:
                    if d['status'] == 'downloading':
                        downloaded = d.get('downloaded_bytes',0)
                        total = d.get('total_bytes',0) or d.get('total_bytes_estimate',0)
                        if total:
                            pct = (downloaded*100)/total
                            speed = d.get('speed',0)
                            sp = sizeof_fmt(speed)+'/s' if speed else ''
                            self.signals.progress.emit(pct)
                            self.signals.status.emit(f"{pct:.1f}% {sp}")
                    elif d['status'] == 'finished':
                        self.signals.progress.emit(100)
                        self.signals.status.emit('Processing...')
                except: pass

            ydl_opts['progress_hooks'] = [progress_hook]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])

            self.signals.finished.emit("Download completed!")
        except Exception as e:
            self.signals.error.emit(str(e))

class GlassDownloader(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Transparent Full HD Video Downloader - Hamza + ChatGPT")
        self.setGeometry(250,100,920,540)
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.container = QtWidgets.QFrame()
        self.container.setObjectName("glassFrame")
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.addWidget(self.container)
        self.container_layout = QtWidgets.QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(18,18,18,18)
        self.container_layout.setSpacing(12)

        # Top bar
        top_bar = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("All Video Downloader")
        title.setStyleSheet("font-weight:700; font-size:16px; color:#e6eef8;")
        top_bar.addWidget(title)
        top_bar.addStretch()
        btn_min = QtWidgets.QPushButton("—"); btn_min.setFixedSize(35,35); btn_min.setObjectName("iconButton"); btn_min.clicked.connect(self.showMinimized)
        btn_close = QtWidgets.QPushButton("✕"); btn_close.setFixedSize(35,35); btn_close.setObjectName("iconButton"); btn_close.clicked.connect(self.close)
        top_bar.addWidget(btn_min); top_bar.addWidget(btn_close)
        self.container_layout.addLayout(top_bar)

        # URL row
        url_row = QtWidgets.QHBoxLayout()
        self.url_edit = QtWidgets.QLineEdit(); self.url_edit.setPlaceholderText("Paste video URL here..."); self.url_edit.setMinimumHeight(45)
        self.fetch_btn = QtWidgets.QPushButton("Fetch Formats"); self.fetch_btn.setObjectName("fetch_btn"); self.fetch_btn.setMinimumHeight(34); self.fetch_btn.clicked.connect(self.fetch_formats)
        url_row.addWidget(self.url_edit); url_row.addWidget(self.fetch_btn)
        self.container_layout.addLayout(url_row)

        # Split layout
        split = QtWidgets.QHBoxLayout()
        left_col = QtWidgets.QVBoxLayout()
        left_col.addWidget(QtWidgets.QLabel("Available Formats:"))
        self.format_list = QtWidgets.QListWidget(); self.format_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection); self.format_list.itemSelectionChanged.connect(self.on_format_select)
        left_col.addWidget(self.format_list)
        split.addLayout(left_col,2)

        right_col = QtWidgets.QVBoxLayout()
        right_col.addWidget(QtWidgets.QLabel("Format Details:"))
        self.details = QtWidgets.QTextEdit(); self.details.setReadOnly(True); self.details.setFixedHeight(160); right_col.addWidget(self.details)
        folder_row = QtWidgets.QHBoxLayout()
        self.folder_edit = QtWidgets.QLineEdit(str(Path.home())); self.folder_edit.setMinimumHeight(30)
        self.folder_btn = QtWidgets.QPushButton("Set Download Folder"); self.folder_btn.setObjectName("folder_btn"); self.folder_btn.clicked.connect(self.select_folder)
        folder_row.addWidget(self.folder_edit); folder_row.addWidget(self.folder_btn)
        right_col.addLayout(folder_row)
        split.addLayout(right_col,1)
        self.container_layout.addLayout(split)

        # Bottom row
        bottom = QtWidgets.QHBoxLayout()
        self.download_btn = QtWidgets.QPushButton("Download Selected"); self.download_btn.setObjectName("download_btn"); self.download_btn.setMinimumHeight(36); self.download_btn.clicked.connect(self.start_download); self.download_btn.setEnabled(False)
        bottom.addWidget(self.download_btn)
        self.auto_best = QtWidgets.QCheckBox("Auto-select best if none"); self.auto_best.setChecked(True); bottom.addWidget(self.auto_best)
        self.progress = QtWidgets.QProgressBar(); self.progress.setValue(0); self.progress.setFixedHeight(20); self.progress.setTextVisible(True); bottom.addWidget(self.progress,1)
        self.status_label = QtWidgets.QLabel("Idle"); bottom.addWidget(self.status_label)
        self.container_layout.addLayout(bottom)

        # QSS
        self.setStyleSheet("""
            QFrame#glassFrame {background: rgba(18,18,18,0.78); border-radius:14px; border:1px solid rgba(255,255,255,0.06);}
            QPushButton {background: rgba(255,255,255,0.02); color:#e6eef8; border:2px solid rgba(255,255,255,0.2); border-radius:8px; padding:6px 12px; font-weight:600;}
            QPushButton#fetch_btn:hover {background: rgba(0,180,255,0.2); border-color:#00b4ff;}
            QPushButton#download_btn:hover {background: rgba(0,255,128,0.2); border-color:#00ff80;}
            QPushButton#folder_btn:hover {background: rgba(255,200,0,0.2); border-color:#ffc800;}
            QPushButton#iconButton {background: transparent; border:none; color:#e6eef8;}
            QPushButton#iconButton:hover#iconButton { color:red; }
            QLineEdit, QTextEdit, QListWidget {background: rgba(255,255,255,0.015); color:#e6eef8; border-radius:6px; padding:6px;}
            QProgressBar {background: rgba(255,255,255,0.02); color:#e6eef8; border-radius:6px; text-align:center;}
            QProgressBar::chunk {background: rgba(255,255,255,0.14); border-radius:6px;}
        """)

        self._drag_pos = None
        self.formats = []
        self.info = None
        self.pool = QtCore.QThreadPool()
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        self.ffmpeg_folder = os.path.join(base_path, "ffmpeg")

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and event.position().y()<80:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft(); event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == QtCore.Qt.LeftButton:
            self.move(event.globalPosition().toPoint()-self._drag_pos); event.accept()

    def mouseReleaseEvent(self, event): self._drag_pos=None

    def select_folder(self):
        dlg = QtWidgets.QFileDialog(self,"Select download folder"); dlg.setFileMode(QtWidgets.QFileDialog.Directory); dlg.setOption(QtWidgets.QFileDialog.ShowDirsOnly,True)
        if dlg.exec():
            folders = dlg.selectedFiles()
            if folders: self.folder_edit.setText(folders[0])

    def clean_url(self,url): return url.split("&")[0] if "&" in url else url

    def fetch_formats(self):
        url = self.clean_url(self.url_edit.text().strip())
        if not url: QtWidgets.QMessageBox.warning(self,"Warning","Please enter URL"); return
        self.status_label.setText("Fetching formats..."); self.fetch_btn.setEnabled(False); self.format_list.clear(); self.download_btn.setEnabled(False)
        worker = FetchFormatsWorker(url)
        worker.signals.formats_ready.connect(self._on_formats_ready)
        worker.signals.status.connect(self._set_status)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    @QtCore.Slot(list,dict)
    def _on_formats_ready(self,formats,info):
        self.formats=formats; self.info=info; self.format_list.clear()
        for f in formats:
            fid,ext = f.get('format_id'), f.get('ext')
            res = f.get('resolution') or f.get('height') or ''
            fps = f.get('fps'); note = f.get('format_note') or ''
            size = f.get('filesize') or f.get('filesize_approx') or 0
            fps_str = f"{fps}fps" if fps else ""; size_str = sizeof_fmt(size) if size else ''
            label=f"{fid} | {ext} | {res} | {fps_str} | {note} | {size_str}"; self.format_list.addItem(label)
        self.fetch_btn.setEnabled(True); self.download_btn.setEnabled(True); self.status_label.setText("Formats fetched")

    @QtCore.Slot(str) 
    def _set_status(self,s): self.status_label.setText(s)
    @QtCore.Slot(str) 
    def _on_error(self,err): QtWidgets.QMessageBox.critical(self,"Error",err); self.status_label.setText("Error"); self.fetch_btn.setEnabled(True); self.download_btn.setEnabled(True)

    def on_format_select(self):
        sel=self.format_list.selectedIndexes(); 
        if not sel: return
        fmt=self.formats[sel[0].row()]
        lines=[f"{k}: {fmt.get(k)}" for k in ('format_id','ext','resolution','format_note','fps','acodec','vcodec')]
        size=fmt.get('filesize') or fmt.get('filesize_approx'); lines.append(f"size: {sizeof_fmt(size)}") if size else None
        self.details.setPlainText("\n".join(lines))

    def start_download(self):
        url=self.clean_url(self.url_edit.text().strip())
        if not url: QtWidgets.QMessageBox.warning(self,"Warning","Enter URL first"); return
        sel=self.format_list.selectedIndexes()
        if sel: format_id=self.formats[sel[0].row()].get('format_id')
        else: format_id=self.formats[0].get('format_id') if self.auto_best.isChecked() and self.formats else None
        folder=self.folder_edit.text().strip() or str(Path.home())
        worker=DownloadWorker(url,format_id,folder,self.ffmpeg_folder)
        worker.signals.progress.connect(self._update_progress)
        worker.signals.status.connect(self._set_status)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error_during_download)
        self.download_btn.setEnabled(False); self.fetch_btn.setEnabled(False)
        self.pool.start(worker); self.status_label.setText("Starting download...")

    @QtCore.Slot(float)
    def _update_progress(self,pct): self.progress.setValue(int(pct))
    @QtCore.Slot(str)
    def _on_finished(self,msg): self.progress.setValue(100); self.status_label.setText("Download complete"); QtWidgets.QMessageBox.information(self,"Done",msg); self.download_btn.setEnabled(True); self.fetch_btn.setEnabled(True)
    @QtCore.Slot(str)
    def _on_error_during_download(self,err): QtWidgets.QMessageBox.critical(self,"Download Error",err); self.status_label.setText("Error"); self.download_btn.setEnabled(True); self.fetch_btn.setEnabled(True)

def main():
    app=QtWidgets.QApplication(sys.argv)
    icon_path=resource_path("mylogo.ico")
    if os.path.exists(icon_path): app.setWindowIcon(QtGui.QIcon(icon_path))
    win=GlassDownloader(); win.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()
