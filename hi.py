import sys
import requests
import threading
from PyQt6 import QtCore, QtGui, QtWidgets
import keyboard

class LookupWorker(QtCore.QThread):
    result_ready = QtCore.pyqtSignal(str)

    def __init__(self, query):
        super().__init__()
        self.query = query.strip()

    def run(self):
        if not self.query:
            self.result_ready.emit("")
            return

        # 1. Attempt Free Dictionary API lookup
        try:
            dict_res = requests.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{self.query}",
                timeout=2
            )
            if dict_res.status_code == 200:
                data = dict_res.json()
                if isinstance(data, list) and len(data) > 0:
                    meanings = data[0].get("meanings", [])
                    phonetic = data[0].get("phonetic", "")
                    output = [f"<b>{self.query.title()}</b> <i>{phonetic}</i><br>"]
                    
                    for m in meanings[:2]:
                        pos = m.get("partOfSpeech", "")
                        defs = m.get("definitions", [])
                        if defs:
                            first_def = defs[0].get("definition", "")
                            output.append(f"• <b>[{pos}]</b> {first_def}")
                    
                    self.result_ready.emit("<br>".join(output))
                    return
        except Exception:
            pass

        # 2. Fallback to Wikipedia Summary
        try:
            wiki_res = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{self.query}",
                headers={"User-Agent": "MovieOverlayLookup/1.0"},
                timeout=2
            )
            if wiki_res.status_code == 200:
                data = wiki_res.json()
                extract = data.get("extract", "")
                if extract:
                    title = data.get("title", self.query)
                    self.result_ready.emit(f"<b>{title} (Wikipedia):</b><br>{extract}")
                    return
        except Exception:
            pass

        # 3. Fallback to DuckDuckGo Instant Answer
        try:
            ddg_res = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": self.query, "format": "json", "no_html": "1"},
                timeout=2
            )
            if ddg_res.status_code == 200:
                data = ddg_res.json()
                abstract = data.get("AbstractText", "") or data.get("Definition", "")
                if abstract:
                    self.result_ready.emit(f"<b>DuckDuckGo:</b><br>{abstract}")
                    return
        except Exception:
            pass

        self.result_ready.emit("<i>No definition or summary found.</i>")


class OverlayWindow(QtWidgets.QWidget):
    hotkey_triggered = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.hotkey_triggered.connect(self.activate_overlay)
        self.worker = None
        self.init_ui()

    def init_ui(self):
        # Frameless, translucent HUD, stays on top of full-screen video
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.WindowStaysOnTopHint |
            QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(600, 280)

        # Styling: Dark translucent card with close button styling
        self.setStyleSheet("""
            QWidget#MainContainer {
                background-color: rgba(20, 20, 25, 235);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 12px;
            }
            QLineEdit {
                background: rgba(255, 255, 255, 0.08);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 15px;
            }
            QLineEdit:focus {
                border: 1px solid #4A90E2;
            }
            QTextBrowser {
                background: transparent;
                border: none;
                color: #E0E0E0;
                font-size: 13px;
            }
            QPushButton#CloseButton {
                background-color: transparent;
                color: #888888;
                border: none;
                font-size: 16px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton#CloseButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
            }
            QPushButton#CloseButton:pressed {
                background-color: rgba(235, 75, 75, 0.6);
                color: #FFFFFF;
            }
            QLabel#HintLabel {
                color: #666666;
                font-size: 11px;
            }
        """)

        # Root layout with padding
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # Container Card
        self.container = QtWidgets.QFrame()
        self.container.setObjectName("MainContainer")
        container_layout = QtWidgets.QVBoxLayout(self.container)
        container_layout.setContentsMargins(14, 12, 14, 12)
        container_layout.setSpacing(10)

        # Top Bar (Input box + Close button)
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setSpacing(8)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search word or concept...")
        self.search_input.returnPressed.connect(self.execute_search)
        top_bar.addWidget(self.search_input)

        self.close_btn = QtWidgets.QPushButton("✕")
        self.close_btn.setObjectName("CloseButton")
        self.close_btn.setFixedSize(30, 32)
        self.close_btn.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.close_btn.clicked.connect(self.hide)
        top_bar.addWidget(self.close_btn)

        container_layout.addLayout(top_bar)

        # Output / Results Area
        self.output_view = QtWidgets.QTextBrowser()
        self.output_view.setOpenExternalLinks(True)
        container_layout.addWidget(self.output_view)

        # Bottom Hint Bar
        hint = QtWidgets.QLabel("Press ESC to dismiss")
        hint.setObjectName("HintLabel")
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        container_layout.addWidget(hint)

        root_layout.addWidget(self.container)
        self.center_on_screen()

    def center_on_screen(self):
        screen = QtGui.QGuiApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = int(screen.height() * 0.20)
        self.move(x, y)

    def activate_overlay(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.clear()
        self.output_view.clear()
        self.search_input.setFocus()

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def execute_search(self):
        query = self.search_input.text()
        if not query:
            return
        self.output_view.setHtml("<i>Fetching information...</i>")
        self.worker = LookupWorker(query)
        self.worker.result_ready.connect(self.display_result)
        self.worker.start()

    def display_result(self, html):
        self.output_view.setHtml(html)


def setup_hotkey(app_window):
    keyboard.add_hotkey("ctrl+shift+d", lambda: app_window.hotkey_triggered.emit())


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = OverlayWindow()

    hotkey_thread = threading.Thread(target=setup_hotkey, args=(window,), daemon=True)
    hotkey_thread.start()

    sys.exit(app.exec())