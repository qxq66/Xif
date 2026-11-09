import sys
import os
import re
from collections import OrderedDict
from PIL import Image, PngImagePlugin
import piexif
import piexif.helper

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLineEdit, QCheckBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QTextEdit,
    QStatusBar, QLabel, QSplitter, QGroupBox, QRadioButton, QTabWidget,
    QFormLayout, QScrollArea, QSizePolicy, QStackedWidget, QListWidget,
    QListWidgetItem, QMenu, QDialog, QSpinBox, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QSizeGrip, QStyledItemDelegate,
    QStyle, QInputDialog, QColorDialog, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QPoint, QSize, QEvent, QRect, QUrl, QMimeData
from PyQt6.QtGui import (
    QPixmap, QImage, QIcon, QAction, QPainter, QColor, QScreen, QTransform,
    QGuiApplication, QShortcut, QKeySequence, QPalette, QPen, QBrush, QDrag,
    QTextCharFormat, QTextCursor, QDesktopServices
)

SCRIPT_NAME = os.path.splitext(os.path.basename(sys.argv[0]))[0]
INI_PATH = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), f"{SCRIPT_NAME}.ini")

CONFIG = {
    "window_title": "Metadaten Suite v6.5",
    "window_width": 1400, "window_height": 900,
    "jpeg_scan_buffer_size": 128 * 1024, # 128KB
    "gallery_margin": 10,               # Rand-Abstand der Bildergalerie (in PX)
    "gallery_h_spacing": -30,             # Horizontaler Abstand zwischen den Thumbnails (in PX)
    "gallery_v_spacing": 0,             # Vertikaler Abstand zwischen den Thumbnails (in PX)
    "gallery_frame_padding_h": -18,       # Horizontaler Rahmen-Aufschlag relativ zum Thumbnail (in PX)
    "gallery_frame_padding_v": 2,       # Vertikaler Rahmen-Aufschlag relativ zum Thumbnail (in PX)
    "prompt_highlight_min_width": 360,  # Mindestbreite des Prompt-Highlight-Feldes (in PX)
    "filter_input_min_width": 150,      # Mindestbreite des Filter-Feldes (in PX)
    "colors": {
        "background": "#2b2b2b", "background_light": "#3c3c3c",
        "foreground": "#f0f0f0", "border": "#555555",
        "button": "#555555", "button_hover": "#666666",
        "highlight_background": "#8B0000", "highlight_text": "#ffffff",
        "label_background": "#4a4a4a", "card_header": "#444444"
    },
    "font_family": "Segoe UI, Arial, sans-serif", "font_size": "9pt",
}

DARK_MODE_STYLESHEET = f"""
    QWidget {{ background-color:{CONFIG['colors']['background']}; color:{CONFIG['colors']['foreground']}; font-family:{CONFIG['font_family']}; font-size:{CONFIG['font_size']}; }}
    QMainWindow, QGroupBox, QTabWidget::pane {{ border: 1px solid {CONFIG['colors']['border']}; background-color:{CONFIG['colors']['background_light']}; }}
    QTabWidget QWidget {{ border: none; }}
    QTabBar::tab {{ background-color:{CONFIG['colors']['background']}; padding: 8px 14px; min-width: 120px; border: 1px solid {CONFIG['colors']['border']}; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
    QTabBar::tab:selected {{ background-color: {CONFIG['colors']['background_light']}; font-weight: bold; }}
    QGroupBox {{ border:1px solid {CONFIG['colors']['border']}; border-radius:4px; margin-top:1ex; font-weight:bold; }}
    QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top center; padding:0 3px; }}
    QLineEdit, QTextEdit {{ background-color:{CONFIG['colors']['background']}; border:1px solid {CONFIG['colors']['border']}; border-radius:3px; padding:2px 4px; color:{CONFIG['colors']['foreground']}; }}
    QPushButton {{ background-color:{CONFIG['colors']['button']}; border:1px solid {CONFIG['colors']['button_hover']}; border-radius:4px; padding:4px 8px; min-height:20px; }}
    QPushButton:hover {{ background-color:{CONFIG['colors']['button_hover']}; }}
    QTableWidget, QListWidget {{ background-color:{CONFIG['colors']['background']}; gridline-color:{CONFIG['colors']['background_light']}; border:1px solid {CONFIG['colors']['border']}; selection-background-color: transparent; outline: none; }}
    QListWidget::item {{ background: transparent; border: none; outline: none; margin: 0px; padding: 0px; }}
    QListWidget::item:selected, QListWidget::item:selected:active, QListWidget::item:selected:inactive {{ background: transparent; border: none; outline: none; }}
    QHeaderView::section {{ background-color:{CONFIG['colors']['background_light']}; padding:4px; border:1px solid {CONFIG['colors']['border']}; font-weight:bold; }}
    .CompactCell {{ border: 1px solid {CONFIG['colors']['border']}; background-color: {CONFIG['colors']['background']}; margin: 0px; padding: 2px; }}
    .CompactHeader {{ background-color: {CONFIG['colors']['card_header']}; font-weight: bold; border-bottom: 1px solid {CONFIG['colors']['border']}; padding: 2px; }}
"""

class ThumbnailDelegate(QStyledItemDelegate):
    """Custom Item Delegate, um Thumbnails ohne Qt-Farbfilter zu zeichnen und den Rahmen flexibel anzupassen."""
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        padding_h = CONFIG.get("gallery_frame_padding_h", 6)
        padding_v = CONFIG.get("gallery_frame_padding_v", 6)

        icon = index.data(Qt.ItemDataRole.DecorationRole)
        pixmap = QPixmap()
        if isinstance(icon, QIcon) and not icon.isNull():
            sizes = icon.availableSizes()
            target_size = sizes[0] if sizes else option.decorationSize
            pixmap = icon.pixmap(target_size)

        pw = pixmap.width() if not pixmap.isNull() else 100
        ph = pixmap.height() if not pixmap.isNull() else 100

        font_metrics = painter.fontMetrics()
        text_h = font_metrics.height()
        text_gap = 4

        # Exakte Inhaltshöhe (Bild + Abstand + Dateiname)
        content_w = pw
        content_h = ph + text_gap + text_h

        # Rahmenabmessungen exakt basierend auf den Padding-Variablen
        frame_w = content_w + (2 * padding_h)
        frame_h = content_h + (2 * padding_v)

        # Rahmen mittig in der Elementzelle platzieren
        frame_x = rect.x() + (rect.width() - frame_w) // 2
        frame_y = rect.y() + (rect.height() - frame_h) // 2
        frame_rect = QRect(frame_x, frame_y, frame_w, frame_h)

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        # Auswahlrahmen und Hintergrund zeichnen
        if is_selected:
            bg_color = QColor(255, 255, 255, 25)
            border_color = QColor("#0078d4") # Kräftiges Blau für Auswahl-Rahmen
            painter.setPen(QPen(border_color, 2))
            painter.setBrush(QBrush(bg_color))
            painter.drawRoundedRect(frame_rect, 4, 4)

        # Thumbnail unverfälscht zeichnen
        if not pixmap.isNull():
            px = frame_x + padding_h
            py = frame_y + padding_v
            painter.drawPixmap(px, py, pixmap)

        # Dateiname zentriert unter dem Thumbnail rendern
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text:
            elided_text = font_metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, pw)
            text_rect = QRect(frame_x + padding_h, frame_y + padding_v + ph + text_gap, pw, text_h + 2)
            
            painter.setPen(QPen(QColor(CONFIG['colors']['foreground'])))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, elided_text)

        painter.restore()

class ThumbnailListWidget(QListWidget):
    """QListWidget mit Explorer-Funktionalitäten: Drag out nach Windows Explorer, Ctrl+X (Ausschneiden) & F2 (Umbenennen)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)

    def startDrag(self, supportedActions):
        selected_items = self.selectedItems()
        if not selected_items:
            return

        urls = []
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and os.path.exists(path):
                urls.append(QUrl.fromLocalFile(path))

        if not urls:
            return

        mime_data = QMimeData()
        mime_data.setUrls(urls)

        drag = QDrag(self)
        drag.setMimeData(mime_data)

        if selected_items[0].icon():
            drag.setPixmap(selected_items[0].icon().pixmap(QSize(100, 100)))

        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F2:
            main_win = self.window()
            if hasattr(main_win, 'rename_selected_file'):
                main_win.rename_selected_file()
                return
        elif event.key() == Qt.Key.Key_F3:
            selected_items = self.selectedItems()
            if selected_items:
                path = selected_items[0].data(Qt.ItemDataRole.UserRole)
                if path and os.path.exists(path):
                    if hasattr(os, 'startfile'):
                        os.startfile(path)
                    else:
                        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        elif event.key() == Qt.Key.Key_F5:
            main_win = self.window()
            if hasattr(main_win, 'refresh_editor_directory'):
                main_win.refresh_editor_directory()
                return
        elif event.matches(QKeySequence.StandardKey.Cut): # Ctrl+X
            main_win = self.window()
            if hasattr(main_win, 'cut_selected_files'):
                main_win.cut_selected_files()
                return
        super().keyPressEvent(event)

class SettingsDialog(QDialog):
    """Sub-GUI für selten benötigte Einstellungen wie Thumbnail-Abmessungen & Highlight-Farben."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.setWindowTitle("Einstellungen")
        self.resize(360, 260)
        self.setStyleSheet(DARK_MODE_STYLESHEET)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.spin_port_w = QSpinBox()
        self.spin_port_w.setRange(50, 800)
        self.spin_port_w.setValue(parent.spin_port_w.value())
        self.spin_port_w.setSuffix("px")

        self.spin_port_h = QSpinBox()
        self.spin_port_h.setRange(50, 800)
        self.spin_port_h.setValue(parent.spin_port_h.value())
        self.spin_port_h.setSuffix("px")

        self.spin_land_w = QSpinBox()
        self.spin_land_w.setRange(50, 800)
        self.spin_land_w.setValue(parent.spin_land_w.value())
        self.spin_land_w.setSuffix("px")

        self.spin_land_h = QSpinBox()
        self.spin_land_h.setRange(50, 800)
        self.spin_land_h.setValue(parent.spin_land_h.value())
        self.spin_land_h.setSuffix("px")

        port_box = QHBoxLayout()
        port_box.addWidget(self.spin_port_w)
        port_box.addWidget(QLabel("x"))
        port_box.addWidget(self.spin_port_h)

        land_box = QHBoxLayout()
        land_box.addWidget(self.spin_land_w)
        land_box.addWidget(QLabel("x"))
        land_box.addWidget(self.spin_land_h)

        form_layout.addRow(QLabel("Thumbs Hochformat:"), port_box)
        form_layout.addRow(QLabel("Thumbs Querformat:"), land_box)

        # Highlight Farbauswahl
        self.bg_color = parent.prompt_highlight_bg
        self.fg_color = parent.prompt_highlight_fg

        self.btn_bg_color = QPushButton(self.bg_color)
        self.btn_bg_color.setStyleSheet(f"background-color: {self.bg_color}; color: {self.fg_color}; font-weight: bold;")
        self.btn_bg_color.clicked.connect(self.choose_bg_color)

        self.btn_fg_color = QPushButton(self.fg_color)
        self.btn_fg_color.setStyleSheet(f"background-color: {self.fg_color}; color: {self.bg_color}; font-weight: bold;")
        self.btn_fg_color.clicked.connect(self.choose_fg_color)

        form_layout.addRow(QLabel("Prompt Highlight BG:"), self.btn_bg_color)
        form_layout.addRow(QLabel("Prompt Highlight Text:"), self.btn_fg_color)

        layout.addLayout(form_layout)

        self.apply_thumbs_btn = QPushButton("Übernehmen & Schließen")
        self.apply_thumbs_btn.clicked.connect(self.apply_changes)
        layout.addWidget(self.apply_thumbs_btn)

    def choose_bg_color(self):
        color = QColorDialog.getColor(QColor(self.bg_color), self, "Hintergrundfarbe wählen")
        if color.isValid():
            self.bg_color = color.name()
            self.btn_bg_color.setText(self.bg_color)
            self.btn_bg_color.setStyleSheet(f"background-color: {self.bg_color}; color: {self.fg_color}; font-weight: bold;")

    def choose_fg_color(self):
        color = QColorDialog.getColor(QColor(self.fg_color), self, "Textfarbe wählen")
        if color.isValid():
            self.fg_color = color.name()
            self.btn_fg_color.setText(self.fg_color)
            self.btn_fg_color.setStyleSheet(f"background-color: {self.fg_color}; color: {self.bg_color}; font-weight: bold;")

    def apply_changes(self):
        self.parent_app.spin_port_w.setValue(self.spin_port_w.value())
        self.parent_app.spin_port_h.setValue(self.spin_port_h.value())
        self.parent_app.spin_land_w.setValue(self.spin_land_w.value())
        self.parent_app.spin_land_h.setValue(self.spin_land_h.value())
        self.parent_app.prompt_highlight_bg = self.bg_color
        self.parent_app.prompt_highlight_fg = self.fg_color
        self.parent_app.update_thumbnail_dimensions()
        self.parent_app.apply_prompt_highlight()
        self.accept()

class ImageLabel(QLabel):
    """Vorschaubild Label mit Aspect-Ratio Skalierung."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        self.pixmap = QPixmap()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def setPixmap(self, pixmap):
        self.pixmap = pixmap
        self.resizeEvent(None)

    def resizeEvent(self, event):
        if not self.pixmap.isNull():
            super().setPixmap(self.pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

class ImageViewerDialog(QDialog):
    """Vollbild-Anzeige Dialog mit Maus-Mover, freier Skalierung und Mausrad-/Pfeiltasten-Navigation."""
    def __init__(self, parent=None, file_list=None, current_index=0):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("background-color: #1a1a1a; color: white;")

        self.file_list = file_list or []
        self.current_index = current_index
        self.parent_app = parent
        self.current_pixmap = QPixmap()
        self.setMinimumSize(250, 200)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Header Info Bar
        self.info_header = QLabel(self)
        self.info_header.setStyleSheet("background-color: rgba(0,0,0,180); color: white; padding: 6px; font-weight: bold; font-size: 11pt;")
        self.info_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.info_header)

        # Scrollbarer / Draggbarer Grafik-Ansichtsbereich
        self.view = QGraphicsView(self)
        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # EventFilter und FocusPolicy setzen, damit Pfeiltasten nicht vom Scrollbar geschluckt werden
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)
        self.installEventFilter(self)

        self.layout.addWidget(self.view)

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        # QSizeGrip unten rechts für freie Größenänderung mit der Maus
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("background-color: rgba(255, 255, 255, 40); width: 16px; height: 16px;")

        self.drag_position = QPoint()
        self.is_window_dragging = False

        # Position und Größe aus der INI laden oder zentrieren
        settings = QSettings(INI_PATH, QSettings.Format.IniFormat)
        saved_geo = settings.value("viewer_geometry")
        if saved_geo:
            self.restoreGeometry(saved_geo)
        else:
            screen = QGuiApplication.primaryScreen()
            screen_geo = screen.availableGeometry() if screen else self.screen().geometry()
            init_w = int(screen_geo.width() * 0.6)
            init_h = int(screen_geo.height() * 0.6)
            self.resize(init_w, init_h)
            if screen:
                center_point = screen.availableGeometry().center()
                self.move(center_point.x() - init_w // 2, center_point.y() - init_h // 2)

        self.load_current_image()

    def update_image_scale(self):
        """Skaliert das aktuell geladene Pixmap dynamisch zur Fenstergröße."""
        if self.current_pixmap.isNull():
            return

        avail_w = max(50, self.width())
        avail_h = max(50, self.height() - self.info_header.height())

        scaled_pixmap = self.current_pixmap.scaled(
            avail_w, avail_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self.pixmap_item.setPixmap(scaled_pixmap)
        self.scene.setSceneRect(0, 0, scaled_pixmap.width(), scaled_pixmap.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'size_grip'):
            self.size_grip.move(self.width() - self.size_grip.width(), self.height() - self.size_grip.height())
            self.size_grip.raise_()
        self.update_image_scale()

    def load_current_image(self):
        if not self.file_list or not (0 <= self.current_index < len(self.file_list)):
            return

        file_path = self.file_list[self.current_index]
        filename = os.path.basename(file_path)
        self.current_pixmap = QPixmap(file_path)

        if self.current_pixmap.isNull():
            self.info_header.setText(f"Fehler beim Laden: {filename}")
            return

        self.update_image_scale()

        self.info_header.setText(f"[{self.current_index + 1}/{len(self.file_list)}] {filename} ({self.current_pixmap.width()}x{self.current_pixmap.height()}) - Esc/Klick zum Schließen")

        # Synchronisiere Hauptfenster/Dateiauswahl/Metadaten
        if self.parent_app and hasattr(self.parent_app, 'sync_full_image_selection'):
            self.parent_app.sync_full_image_selection(self.current_index)

    def next_image(self):
        """Wechselt zum nächsten Bild in der Liste."""
        if self.file_list and self.current_index < len(self.file_list) - 1:
            self.current_index += 1
            self.load_current_image()

    def prev_image(self):
        """Wechselt zum vorherigen Bild in der Liste."""
        if self.file_list and self.current_index > 0:
            self.current_index -= 1
            self.load_current_image()

    def eventFilter(self, watched, event):
        """Fängt Rechtsklicks, Pfeiltasten und Mausrad-Scrolling auf der Vollbild-Ansicht ab."""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                self.next_image()
                return True
            elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                self.prev_image()
                return True
            elif key in (Qt.Key.Key_Escape, Qt.Key.Key_Return):
                self.close()
                return True

        if watched in (self.view, self.view.viewport(), self):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.RightButton:
                    self.close()
                    return True
            elif event.type() == QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                if delta < 0:
                    self.next_image()
                elif delta > 0:
                    self.prev_image()
                return True
        return super().eventFilter(watched, event)

    def wheelEvent(self, event):
        """Mausrad-Navigation außerhalb des Hauptbildbereichs."""
        delta = event.angleDelta().y()
        if delta < 0:
            self.next_image()
        elif delta > 0:
            self.prev_image()
        event.accept()

    def mousePressEvent(self, event):
        """Schließt das Vollbildfenster per Rechtsklick (auch außerhalb des Bildbereichs)."""
        if event.button() == Qt.MouseButton.RightButton:
            self.close()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.is_window_dragging = True
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_window_dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.is_window_dragging = False

    def closeEvent(self, event):
        """Speichert Position und Größe der Vollansicht in der INI-Datei."""
        settings = QSettings(INI_PATH, QSettings.Format.IniFormat)
        settings.setValue("viewer_geometry", self.saveGeometry())
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return):
            self.close()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.next_image()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.prev_image()

class ProcessingThread(QThread):
    progress = pyqtSignal(str)
    file_finished = pyqtSignal(dict)
    all_finished = pyqtSignal(str)

    def __init__(self, files_to_process, settings):
        super().__init__()
        self.files_to_process = files_to_process
        self.settings = settings
        self.is_running = True

    def run(self):
        mode = self.settings.get("mode", "remove")
        if mode == "remove":
            self._run_remove()
        elif mode == "replace":
            self._run_replace()

    def _run_remove(self):
        raw_terms = [term.strip() for term in self.settings["terms_to_remove"].split(',') if term.strip()]
        if self.settings["use_reference_file"] and os.path.exists("referenz.txt"):
            try:
                with open("referenz.txt", "r", encoding='utf-8') as f:
                    raw_terms.extend([term.strip() for term in f.read().split(',') if term.strip()])
            except Exception as e:
                self.progress.emit(f"Fehler bei referenz.txt: {e}")
        terms_to_remove = list(dict.fromkeys(raw_terms))
        if not terms_to_remove:
            self.all_finished.emit("Abgeschlossen. Keine Begriffe zum Entfernen angegeben.")
            return
        total_removals = 0
        for i, (file_path, row) in enumerate(self.files_to_process.items()):
            if not self.is_running:
                break
            self.progress.emit(f"Verarbeite Datei {i+1}/{len(self.files_to_process)}: {os.path.basename(file_path)}")
            if file_path.lower().endswith('.png'):
                result = self._process_png_file_remove(file_path, terms_to_remove)
            elif file_path.lower().endswith(('.jpg', '.jpeg')):
                result = self._process_jpeg_file_binary_remove(file_path, terms_to_remove)
            else:
                result = {"file_path": file_path, "original_meta": "", "changed_strings": [], "status": "Dateityp nicht unterstützt"}
            result["row"] = row
            total_removals += len(result.get("changed_strings", []))
            self.file_finished.emit(result)
        self.all_finished.emit(f"Abgeschlossen. {total_removals} Begriffe aus {len(self.files_to_process)} Bildern entfernt.")

    def _run_replace(self):
        search_term = self.settings.get("search_term")
        replace_term = self.settings.get("replace_term")
        if not search_term:
            self.all_finished.emit("Abgeschlossen. Kein Suchbegriff angegeben.")
            return
        total_replaces = 0
        for i, (file_path, row) in enumerate(self.files_to_process.items()):
            if not self.is_running:
                break
            self.progress.emit(f"Ersetze in Datei {i+1}/{len(self.files_to_process)}: {os.path.basename(file_path)}")
            if file_path.lower().endswith('.png'):
                result = self._process_png_file_replace(file_path, search_term, replace_term)
            else:
                result = {"file_path": file_path, "original_meta": "", "changed_strings": [], "status": "Ersetzen für JPEG nicht unterstützt"}
            result["row"] = row
            if result.get("status") == "Gespeichert":
                total_replaces += 1
            self.file_finished.emit(result)
        self.all_finished.emit(f"Abgeschlossen. '{search_term}' wurde in {total_replaces} von {len(self.files_to_process)} Bildern ersetzt.")

    @staticmethod
    def _get_png_parameters(file_path):
        try:
            img = Image.open(file_path)
            return (img, img.info['parameters']) if 'parameters' in img.info else (None, None)
        except Exception:
            return None, None

    def _process_jpeg_file_binary_remove(self, file_path, terms_to_remove):
        try:
            with open(file_path, 'rb') as f:
                original_data = f.read()
        except Exception as e:
            return {"file_path": file_path, "status": f"Lesefehler: {e}"}
        scan_size = CONFIG["jpeg_scan_buffer_size"]
        header_buffer = bytearray(original_data[:scan_size])
        tail = original_data[scan_size:]
        removed_terms_details = []
        for term in terms_to_remove:
            if term.endswith(':'):
                pattern = re.compile(re.escape(term.encode('utf-8')) + b'[^,]*', re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(term.encode('utf-8')), re.IGNORECASE)
            for match in reversed(list(pattern.finditer(header_buffer))):
                start, end = match.span()
                found_term = header_buffer[start:end].decode('utf-8', 'ignore')
                header_buffer[start:end] = b' ' * (end - start)
                removed_terms_details.append(found_term)
        if not removed_terms_details:
            return {"file_path": file_path, "original_meta": "N/A (Binär-Modus)", "changed_strings": [], "status": "Begriffe nicht gefunden"}
        output_path = file_path
        if not self.settings["overwrite"]:
            base, ext = os.path.splitext(file_path)
            output_path = f"{base}_modified{ext}"
        try:
            with open(output_path, 'wb') as f:
                f.write(header_buffer)
                f.write(tail)
        except Exception as e:
            return {"file_path": file_path, "original_meta": "N/A (Binär-Modus)", "changed_strings": removed_terms_details, "status": f"Schreibfehler: {e}"}
        return {"file_path": file_path, "original_meta": "N/A (Binär-Modus)", "changed_strings": list(set(removed_terms_details)), "status": "Gespeichert (Binär)"}

    def _process_png_file_remove(self, file_path, terms_to_remove):
        img, original_meta = self._get_png_parameters(file_path)
        if not original_meta:
            return {"file_path": file_path, "original_meta": "", "changed_strings": [], "status": "Keine Metadaten gefunden"}
        flat_meta_string = original_meta.replace('\n', ',')
        original_tags = [tag.strip() for tag in flat_meta_string.split(',') if tag.strip()]
        kept_tags, removed_tags = [], []
        for tag in original_tags:
            tag_was_removed = False
            for term in terms_to_remove:
                term_lower, tag_lower = term.lower(), tag.lower()
                is_colon_rule = term_lower.endswith(':')
                if is_colon_rule:
                    prefix = term_lower[:-1]
                    if tag_lower.startswith(prefix + ':') or tag_lower == prefix:
                        tag_was_removed = True
                elif tag_lower == term_lower:
                    tag_was_removed = True
                if tag_was_removed:
                    removed_tags.append(tag)
                    break
            if not tag_was_removed:
                kept_tags.append(tag)
        if not removed_tags:
            return {"file_path": file_path, "original_meta": original_meta, "changed_strings": [], "status": "Begriffe nicht gefunden"}
        new_meta = ", ".join(kept_tags)
        output_path = file_path
        if not self.settings["overwrite"]:
            base, ext = os.path.splitext(file_path)
            output_path = f"{base}_modified{ext}"
        try:
            temp_img = Image.open(file_path)
            png_info = PngImagePlugin.PngInfo()
            for key, value in temp_img.info.items():
                if key != 'parameters':
                    png_info.add_text(key, value)
            if new_meta:
                png_info.add_text('parameters', new_meta)
            temp_img.save(output_path, "png", pnginfo=png_info)
            status = "Gespeichert"
        except Exception as e:
            status = f"Speicherfehler: {e}"
        return {"file_path": file_path, "original_meta": original_meta, "changed_strings": removed_tags, "status": status}

    def _process_png_file_replace(self, file_path, search, replace):
        img, original_meta = self._get_png_parameters(file_path)
        if not original_meta or search not in original_meta:
            return {"file_path": file_path, "original_meta": original_meta, "changed_strings": [], "status": "Begriff nicht gefunden"}
        modified_meta = original_meta.replace(search, replace)
        output_path = file_path
        if not self.settings["overwrite"]:
            base, ext = os.path.splitext(file_path)
            output_path = f"{base}_modified{ext}"
        try:
            png_info = PngImagePlugin.PngInfo()
            for key, value in img.info.items():
                if key != 'parameters':
                    png_info.add_text(key, value)
            if modified_meta:
                png_info.add_text('parameters', modified_meta)
            img.save(output_path, "png", pnginfo=png_info)
            status = "Gespeichert"
        except Exception as e:
            status = f"Speicherfehler: {e}"
        return {"file_path": file_path, "original_meta": original_meta, "changed_strings": [search], "status": status}

    def stop(self):
        self.is_running = False

class ExifEditorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(CONFIG["window_title"])
        self.setGeometry(100, 100, CONFIG["window_width"], CONFIG["window_height"])
        self.setAcceptDrops(True)
        
        self.current_editor_file = None
        self.current_editor_dir = os.path.expanduser("~")
        self.editor_widgets = OrderedDict()
        self.file_paths = []
        self.thread = None
        self.file_data_store = {}
        
        # Highlight Farben & Historie für das Prompt-Feld
        self.prompt_highlight_bg = "#8B0000"
        self.prompt_highlight_fg = "#ffffff"
        self.prompt_highlight_history = []

        # Standard-Thumbnail Abmessungen
        self.thumb_portrait_w = 200
        self.thumb_portrait_h = 300
        self.thumb_landscape_w = 300
        self.thumb_landscape_h = 200

        self.spin_port_w = QSpinBox()
        self.spin_port_w.setRange(50, 800)
        self.spin_port_w.setValue(self.thumb_portrait_w)

        self.spin_port_h = QSpinBox()
        self.spin_port_h.setRange(50, 800)
        self.spin_port_h.setValue(self.thumb_portrait_h)

        self.spin_land_w = QSpinBox()
        self.spin_land_w.setRange(50, 800)
        self.spin_land_w.setValue(self.thumb_landscape_w)

        self.spin_land_h = QSpinBox()
        self.spin_land_h.setRange(50, 800)
        self.spin_land_h.setValue(self.thumb_landscape_h)

        self.initUI()
        self.setStyleSheet(DARK_MODE_STYLESHEET)
        self.load_settings()

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.tab2 = QWidget()
        self.tabs.addTab(self.tab2, "Metadaten-Editor (PNG/JPEG)")
        self.init_tab2_ui()

        self.tab1 = QWidget()
        self.tabs.addTab(self.tab1, "Massenverarbeitung")
        self.init_tab1_ui()

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Bereit.")

        # Button "Set" unten rechts auf gleicher Höhe wie die Statuszeile
        self.set_settings_btn = QPushButton("Set")
        self.set_settings_btn.setStyleSheet("padding: 2px 10px; font-weight: bold;")
        self.set_settings_btn.clicked.connect(self.open_settings_dialog)
        self.statusBar.addPermanentWidget(self.set_settings_btn)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if len(files) == 1 and files[0].lower().endswith(('.png', '.jpg', '.jpeg')):
            self.tabs.setCurrentWidget(self.tab2)
            folder = os.path.dirname(files[0])
            self.load_directory_in_editor_list(folder)
            # Finde und selektiere die genaue Datei
            for i in range(self.thumb_list.count()):
                item = self.thumb_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == files[0]:
                    self.thumb_list.setCurrentItem(item)
                    break
        elif len(files) > 0:
            folder = os.path.dirname(files[0]) if os.path.isfile(files[0]) else files[0]
            self.load_directory_in_editor_list(folder)

    def init_tab1_ui(self):
        tab1_layout = QHBoxLayout(self.tab1)
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)

        file_select_group = QGroupBox("Dateiauswahl")
        file_select_layout = QVBoxLayout()
        self.file_select_btn = QPushButton("Bilder auswählen")
        self.file_select_btn.clicked.connect(self.select_files)
        self.selected_files_label = QLabel("Keine Dateien ausgewählt.")
        self.selected_files_label.setWordWrap(True)
        file_select_layout.addWidget(self.file_select_btn)
        file_select_layout.addWidget(self.selected_files_label)
        file_select_group.setLayout(file_select_layout)

        mode_group = QGroupBox("Aktionsmodus")
        mode_layout = QVBoxLayout()
        self.remove_radio = QRadioButton("Begriffe entfernen")
        self.replace_radio = QRadioButton("Suchen & Ersetzen")
        self.remove_radio.setChecked(True)
        self.remove_radio.toggled.connect(self.toggle_mode)
        mode_layout.addWidget(self.remove_radio)
        mode_layout.addWidget(self.replace_radio)
        mode_group.setLayout(mode_layout)

        self.remove_group = QGroupBox("Begriffe zum Entfernen")
        remove_layout = QVBoxLayout()
        self.terms_input = QTextEdit()
        self.terms_input.setPlaceholderText("wort, anderes wort, beispiel:\nJeden Begriff durch ein Komma trennen.")
        self.terms_input.setMinimumHeight(80)
        self.ref_file_checkbox = QCheckBox("Referenzliste 'referenz.txt' verwenden")
        self.ref_file_checkbox.setChecked(True)
        remove_layout.addWidget(self.terms_input)
        remove_layout.addWidget(self.ref_file_checkbox)
        self.remove_group.setLayout(remove_layout)

        self.replace_group = QGroupBox("Suchen und Ersetzen")
        replace_layout = QVBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Suchen nach...")
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Ersetzen durch...")
        replace_layout.addWidget(QLabel("Suchen:"))
        replace_layout.addWidget(self.search_input)
        replace_layout.addWidget(QLabel("Ersetzen:"))
        replace_layout.addWidget(self.replace_input)
        self.replace_group.setLayout(replace_layout)
        self.replace_group.setVisible(False)

        options_group = QGroupBox("Optionen")
        options_layout = QVBoxLayout()
        self.overwrite_checkbox = QCheckBox("Originaldateien überschreiben")
        options_layout.addWidget(self.overwrite_checkbox)
        options_group.setLayout(options_layout)

        self.start_stop_btn = QPushButton("Start")
        self.start_stop_btn.clicked.connect(self.start_stop_processing)

        control_layout.addWidget(file_select_group)
        control_layout.addWidget(mode_group)
        control_layout.addWidget(self.remove_group)
        control_layout.addWidget(self.replace_group)
        control_layout.addWidget(options_group)
        control_layout.addWidget(self.start_stop_btn)
        control_layout.addStretch()

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["Dateiname", "Geänderte Begriffe", "Status"])
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_table.setSortingEnabled(True)
        self.result_table.cellClicked.connect(self.handle_table_cell_click)
        self.result_table.itemDoubleClicked.connect(self.handle_table_double_click)

        self.display_stack = QStackedWidget()
        self.meta_display = QTextEdit()
        self.meta_display.setReadOnly(True)
        self.image_preview_label = ImageLabel()
        self.display_stack.addWidget(self.meta_display)
        self.display_stack.addWidget(self.image_preview_label)

        self.tab1_result_splitter = QSplitter(Qt.Orientation.Vertical)
        self.tab1_result_splitter.addWidget(self.result_table)
        self.tab1_result_splitter.addWidget(self.display_stack)

        self.tab1_main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tab1_main_splitter.addWidget(control_panel)
        self.tab1_main_splitter.addWidget(self.tab1_result_splitter)
        self.tab1_main_splitter.setSizes([300, 1100])
        tab1_layout.addWidget(self.tab1_main_splitter)

    def init_tab2_ui(self):
        editor_layout = QVBoxLayout(self.tab2)

        # Top Action Bar mit Ordner-Button, Filter-Inputbox, Filter-Button, Prompt-Highlight-Inputbox und Save-Button
        top_bar_layout = QHBoxLayout()
        self.open_dir_btn = QPushButton("Ordner")
        self.open_dir_btn.clicked.connect(self.select_editor_directory)
        top_bar_layout.addWidget(self.open_dir_btn)

        # Filter-Eingabefeld mit RegEx-Unterstützung und Button
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Metadaten-Filter (RegEx)...")
        self.filter_input.setMinimumWidth(CONFIG["filter_input_min_width"])
        self.filter_input.returnPressed.connect(self.filter_thumbnails)
        top_bar_layout.addWidget(self.filter_input)

        self.filter_btn = QPushButton("Filter")
        self.filter_btn.clicked.connect(self.on_filter_btn_clicked)
        top_bar_layout.addWidget(self.filter_btn)

        # Prompt Highlight Eingabebox mit RegEx-Unterstützung und Historie (Drop-Down)
        self.prompt_highlight_input = QComboBox()
        self.prompt_highlight_input.setEditable(True)
        if self.prompt_highlight_input.lineEdit():
            self.prompt_highlight_input.lineEdit().setPlaceholderText("Prompt hervorheben (RegEx)...")
            self.prompt_highlight_input.lineEdit().returnPressed.connect(self.add_prompt_highlight_to_history)
        self.prompt_highlight_input.setMinimumWidth(CONFIG["prompt_highlight_min_width"])
        self.prompt_highlight_input.currentTextChanged.connect(self.apply_prompt_highlight)
        top_bar_layout.addWidget(self.prompt_highlight_input)

        top_bar_layout.addStretch()

        self.editor_save_btn = QPushButton("Save")
        self.editor_save_btn.clicked.connect(self.save_editor_changes)
        top_bar_layout.addWidget(self.editor_save_btn)

        editor_layout.addLayout(top_bar_layout)

        # Haupt-Splitter Horizontal (Links: Thumbnail-Gitter, Rechts: Kompakter Metadaten-Editor)
        self.tab2_main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # LINKER BEREICH: Thumbnail Galerie
        thumb_container = QGroupBox("Bilder Galerie (Thumbnails)")
        thumb_layout = QVBoxLayout(thumb_container)
        
        gallery_margin = CONFIG.get("gallery_margin", 10)
        thumb_layout.setContentsMargins(gallery_margin, gallery_margin, gallery_margin, gallery_margin)

        # Nutzt die erweiterte ThumbnailListWidget Klasse für Explorer-Funktionalität
        self.thumb_list = ThumbnailListWidget()
        self.thumb_list.setItemDelegate(ThumbnailDelegate(self.thumb_list))

        self.thumb_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumb_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumb_list.setMovement(QListWidget.Movement.Static)
        self.thumb_list.setSpacing(0)
        self.thumb_list.setWordWrap(True)
        self.thumb_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.thumb_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumb_list.customContextMenuRequested.connect(self.show_file_list_context_menu)

        # Tastenkombination Strg+C / Ctrl+C für Copy Prompts auf der Thumbnail-Liste
        self.copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self.thumb_list)
        self.copy_shortcut.activated.connect(self.copy_selected_prompts)
        
        # Tastenkombination F5 zum Aktualisieren der Dateiliste & Thumbnails
        self.f5_shortcut = QShortcut(QKeySequence("F5"), self.tab2)
        self.f5_shortcut.activated.connect(self.refresh_editor_directory)

        # Pfeil-Tasten & Auswahl-Events verbinden
        self.thumb_list.itemSelectionChanged.connect(self.on_thumb_selection_changed)
        self.thumb_list.itemDoubleClicked.connect(self.on_thumb_double_clicked)

        thumb_layout.addWidget(self.thumb_list)
        self.tab2_main_splitter.addWidget(thumb_container)

        # RECHTER BEREICH: Kompakter Metadaten-Editor
        editor_group = QGroupBox("Metadaten-Editor (Kompakte Ansicht)")
        editor_group_layout = QVBoxLayout(editor_group)
        editor_group_layout.setContentsMargins(4, 4, 4, 4)

        # Splitter für dynamische Höhenanpassung des "Prompt"-Feldes
        self.editor_splitter = QSplitter(Qt.Orientation.Vertical)

        # 1. Obere Hälfte im Splitter: Resizbares Prompt Feld
        prompt_box = QWidget()
        prompt_layout = QVBoxLayout(prompt_box)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.addWidget(QLabel("Prompt:"))
        self.prompt_text_edit = QTextEdit()
        self.prompt_text_edit.setPlaceholderText("Haupt-Prompt...")
        prompt_layout.addWidget(self.prompt_text_edit)
        self.editor_splitter.addWidget(prompt_box)

        # 2. Untere Hälfte im Splitter: Scrollbereich für übrige kompakte Metadaten-Felder
        self.compact_scroll = QScrollArea()
        self.compact_scroll.setWidgetResizable(True)
        self.compact_container = QWidget()
        self.compact_container_layout = QVBoxLayout(self.compact_container)
        self.compact_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.compact_container_layout.setSpacing(4)
        self.compact_container_layout.setContentsMargins(2, 2, 2, 2)
        self.compact_scroll.setWidget(self.compact_container)
        self.editor_splitter.addWidget(self.compact_scroll)

        # Initiales Größenverhältnis für Prompt vs Parameter
        self.editor_splitter.setSizes([180, 500])

        editor_group_layout.addWidget(self.editor_splitter)
        self.tab2_main_splitter.addWidget(editor_group)

        self.tab2_main_splitter.setSizes([600, 800])
        editor_layout.addWidget(self.tab2_main_splitter)

    def apply_prompt_highlight(self):
        """Hebt die eingegebene Zeichenkette/RegEx im Prompt-Feld in Echtzeit hervor."""
        if not hasattr(self, 'prompt_highlight_input') or not hasattr(self, 'prompt_text_edit'):
            return

        search_text = self.prompt_highlight_input.currentText()
        extra_selections = []

        if search_text and self.prompt_text_edit.toPlainText():
            doc = self.prompt_text_edit.document()
            prompt_text = self.prompt_text_edit.toPlainText()

            try:
                pattern = re.compile(search_text, re.IGNORECASE)
            except re.error:
                pattern = re.compile(re.escape(search_text), re.IGNORECASE)

            fmt = QTextCharFormat()
            fmt.setBackground(QColor(self.prompt_highlight_bg))
            fmt.setForeground(QColor(self.prompt_highlight_fg))

            for match in pattern.finditer(prompt_text):
                start, end = match.span()
                if start == end: # Verhindert Endlosschleifen bei leeren Matches
                    continue
                cursor = QTextCursor(doc)
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

                selection = QTextEdit.ExtraSelection()
                selection.format = fmt
                selection.cursor = cursor
                extra_selections.append(selection)

        self.prompt_text_edit.setExtraSelections(extra_selections)

    def add_prompt_highlight_to_history(self):
        """Fügt den aktuellen Suchbegriff der Historie hinzu (maximal 15 Einträge)."""
        text = self.prompt_highlight_input.currentText().strip()
        if not text:
            return

        if text in self.prompt_highlight_history:
            self.prompt_highlight_history.remove(text)
        self.prompt_highlight_history.insert(0, text)
        self.prompt_highlight_history = self.prompt_highlight_history[:15]

        self.prompt_highlight_input.blockSignals(True)
        self.prompt_highlight_input.clear()
        self.prompt_highlight_input.addItems(self.prompt_highlight_history)
        self.prompt_highlight_input.setCurrentText(text)
        self.prompt_highlight_input.blockSignals(False)

    def on_filter_btn_clicked(self):
        """Verwaltet die Doppelfunktion des Buttons (Filter vs. Reset)."""
        if self.filter_btn.text() == "Reset":
            self.filter_input.clear()
            self.filter_btn.setText("Filter")
            self.refresh_editor_directory()
        else:
            self.filter_thumbnails()

    def refresh_editor_directory(self):
        """Lädt das aktuelle Verzeichnis neu und aktualisiert die Thumbnail-Liste (z. B. nach Verschieben oder F5)."""
        if self.current_editor_dir:
            self.load_directory_in_editor_list(self.current_editor_dir)

    def filter_thumbnails(self):
        """Ressourcenschonende Metadaten-Filterung mit RegEx: Durchsucht die Text-Metadaten der geladenen Bilder."""
        query = self.filter_input.text().strip()
        total_items = self.thumb_list.count()
        if not query:
            for i in range(total_items):
                self.thumb_list.item(i).setHidden(False)
            self.filter_btn.setText("Filter")
            self.statusBar.showMessage(f"Filter zurückgesetzt ({total_items} Bilder).")
            return

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        visible_count = 0
        for i in range(total_items):
            item = self.thumb_list.item(i)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            meta_string = ""

            if file_path.lower().endswith('.png'):
                _, meta_string = self._get_png_parameters(file_path)
            elif file_path.lower().endswith(('.jpg', '.jpeg')):
                meta_string = self._get_jpeg_meta_string(file_path)

            match = bool(pattern.search(meta_string))
            item.setHidden(not match)
            if match:
                visible_count += 1

        self.filter_btn.setText("Reset")
        self.statusBar.showMessage(f"Filter '{query}' (RegEx): {visible_count} von {total_items} Bildern angezeigt.")

    def rename_selected_file(self):
        """Ermöglicht das Umbenennen der Datei mit F2 (wie im Windows Explorer)."""
        selected_items = self.thumb_list.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        old_path = item.data(Qt.ItemDataRole.UserRole)
        if not old_path or not os.path.exists(old_path):
            return

        dir_name, old_filename = os.path.split(old_path)
        new_filename, ok = QInputDialog.getText(
            self, "Datei umbenennen", "Neuer Dateiname:",
            QLineEdit.EchoMode.Normal, old_filename
        )

        if ok and new_filename and new_filename != old_filename:
            new_path = os.path.join(dir_name, new_filename)
            try:
                os.rename(old_path, new_path)
                item.setText(new_filename)
                item.setData(Qt.ItemDataRole.UserRole, new_path)
                if self.current_editor_file == old_path:
                    self.current_editor_file = new_path
                self.statusBar.showMessage(f"Datei umbenannt in '{new_filename}'.")
            except Exception as e:
                self.statusBar.showMessage(f"Fehler beim Umbenennen: {e}")

    def update_thumbnail_dimensions(self):
        self.thumb_portrait_w = self.spin_port_w.value()
        self.thumb_portrait_h = self.spin_port_h.value()
        self.thumb_landscape_w = self.spin_land_w.value()
        self.thumb_landscape_h = self.spin_land_h.value()
        
        # Lade Thumbnail-Liste neu
        if self.current_editor_dir:
            self.load_directory_in_editor_list(self.current_editor_dir)

    def select_editor_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Bilderordner auswählen", self.current_editor_dir)
        if folder:
            self.load_directory_in_editor_list(folder)

    def load_directory_in_editor_list(self, folder_path):
        self.current_editor_dir = folder_path
        self.thumb_list.clear()
        if not os.path.exists(folder_path):
            return
        
        valid_extensions = ('.png', '.jpg', '.jpeg')
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
        files.sort()

        max_grid_w = max(self.thumb_portrait_w, self.thumb_landscape_w)
        max_grid_h = max(self.thumb_portrait_h, self.thumb_landscape_h)
        self.thumb_list.setIconSize(QSize(max_grid_w, max_grid_h))

        h_spacing = CONFIG.get("gallery_h_spacing", 6)
        v_spacing = CONFIG.get("gallery_v_spacing", 6)

        for f in files:
            full_path = os.path.join(folder_path, f)
            pix = QPixmap(full_path)
            if pix.isNull():
                continue

            is_portrait = pix.height() > pix.width()
            target_w = self.thumb_portrait_w if is_portrait else self.thumb_landscape_w
            target_h = self.thumb_portrait_h if is_portrait else self.thumb_landscape_h

            scaled_pix = pix.scaled(
                target_w, target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            # Transparenter Canvas als Platzhalter für konsistente Gitterdarstellung
            canvas = QPixmap(target_w, target_h)
            canvas.fill(QColor(0, 0, 0, 0))
            painter = QPainter(canvas)
            x_off = (target_w - scaled_pix.width()) // 2
            y_off = (target_h - scaled_pix.height()) // 2
            painter.drawPixmap(x_off, y_off, scaled_pix)
            painter.end()

            item = QListWidgetItem(QIcon(canvas), f)
            # Item-Gesamtgröße im Raster: ausschließlich abhängig von Thumbnail-Größe + Text-Höhe + h/v-Spacing
            item_width = target_w + h_spacing
            item_height = target_h + 24 + v_spacing
            item.setSizeHint(QSize(item_width, item_height))
            item.setData(Qt.ItemDataRole.UserRole, full_path)
            self.thumb_list.addItem(item)

        self.statusBar.showMessage(f"{len(files)} Bilder aus Ordner geladen: {folder_path}")

    def on_thumb_selection_changed(self):
        selected_items = self.thumb_list.selectedItems()
        if not selected_items:
            return
        first_file = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if first_file != self.current_editor_file:
            self.load_file_in_editor(first_file)

    def on_thumb_double_clicked(self, item):
        file_path = item.data(Qt.ItemDataRole.UserRole)
        file_list = []
        current_idx = 0

        for i in range(self.thumb_list.count()):
            f_path = self.thumb_list.item(i).data(Qt.ItemDataRole.UserRole)
            file_list.append(f_path)
            if f_path == file_path:
                current_idx = i

        viewer = ImageViewerDialog(self, file_list, current_idx)
        viewer.exec()

    def sync_full_image_selection(self, index):
        """Wird vom Vollbild-Viewer aufgerufen, um das angewählte Bild in der Galerie & im Editor abzugleichen."""
        if 0 <= index < self.thumb_list.count():
            item = self.thumb_list.item(index)
            self.thumb_list.setCurrentItem(item)

    def show_file_list_context_menu(self, position):
        selected_items = self.thumb_list.selectedItems()
        if not selected_items:
            return

        menu = QMenu(self)
        copy_prompts_action = QAction("Copy Prompts", self)
        copy_prompts_action.triggered.connect(self.copy_selected_prompts)
        menu.addAction(copy_prompts_action)
        menu.exec(self.thumb_list.viewport().mapToGlobal(position))

    def copy_selected_prompts(self):
        selected_items = self.thumb_list.selectedItems()
        if not selected_items:
            return

        extracted_prompts = []
        for item in selected_items:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            meta_string = ""
            if file_path.lower().endswith('.png'):
                _, meta_string = self._get_png_parameters(file_path)
            elif file_path.lower().endswith(('.jpg', '.jpeg')):
                meta_string = self._get_jpeg_meta_string(file_path)

            prompt = ""
            if meta_string:
                parsed_data = self._parse_meta_string(meta_string)
                prompt = parsed_data.get("Prompt", "")

            # Bereinigung: Prompt in genau eine Zeile bringen (Zeilenumbrüche entfernen)
            single_line_prompt = " ".join(prompt.splitlines()).strip()
            extracted_prompts.append(single_line_prompt)

        final_clipboard_text = "\n".join(extracted_prompts)
        QApplication.clipboard().setText(final_clipboard_text)
        self.statusBar.showMessage(f"{len(extracted_prompts)} Prompts in die Zwischenablage kopiert.")

    def load_file_in_editor(self, file_path):
        self.current_editor_file = file_path
        
        # Container zurücksetzen
        while self.compact_container_layout.count():
            item = self.compact_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.editor_widgets.clear()
        self.prompt_text_edit.clear()

        meta_string = ""
        if file_path.lower().endswith('.png'):
            _, meta_string = self._get_png_parameters(file_path)
        elif file_path.lower().endswith(('.jpg', '.jpeg')):
            meta_string = self._get_jpeg_meta_string(file_path)

        if not meta_string:
            self.statusBar.showMessage(f"Keine auslesbaren Metadaten in '{os.path.basename(file_path)}' gefunden.")
            self.apply_prompt_highlight()
            return

        parsed_data = self._parse_meta_string(meta_string)
        self._build_compact_editor_ui(parsed_data)
        self.apply_prompt_highlight()
        self.statusBar.showMessage(f"'{os.path.basename(file_path)}' geladen.")

    def _get_png_parameters(self, file_path):
        try:
            img = Image.open(file_path)
            return img, img.info.get('parameters', '')
        except Exception:
            return None, ""

    def _get_jpeg_meta_string(self, file_path):
        try:
            img = Image.open(file_path)
            if "exif" in img.info:
                exif_dict = piexif.load(img.info["exif"])
                if piexif.ExifIFD.UserComment in exif_dict.get("Exif", {}):
                    return piexif.helper.UserComment.load(exif_dict["Exif"][piexif.ExifIFD.UserComment])
                if piexif.ImageIFD.ImageDescription in exif_dict.get("0th", {}):
                    return exif_dict["0th"][piexif.ImageIFD.ImageDescription].decode('utf-8', 'ignore').strip()
        except Exception:
            pass
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(CONFIG["jpeg_scan_buffer_size"])
                match = re.search(r"score_.*Steps: \d+", content)
                if match:
                    return match.group(0)
        except Exception:
            pass
        return ""

    def _parse_meta_string(self, meta_string):
        parsed = OrderedDict()
        if "Negative prompt:" in meta_string:
            parts = meta_string.split("Negative prompt:", 1)
            parsed["Prompt"] = parts[0].strip()
            if "\n" in parts[1]:
                neg_parts = parts[1].split("\n", 1)
                parsed["Negative Prompt"] = neg_parts[0].strip()
                remaining_string = neg_parts[1]
            else:
                parsed["Negative Prompt"] = parts[1].strip()
                remaining_string = ""
        else:
            parts = meta_string.split("\n", 1)
            parsed["Prompt"] = parts[0].strip()
            remaining_string = parts[1] if len(parts) > 1 else ""

        pattern = r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)'
        remaining_parts = re.split(pattern, remaining_string)
        for part in remaining_parts:
            if ':' in part:
                key, value = part.split(':', 1)
                key = key.strip()
                value = value.strip().strip('"')
                if key:
                    parsed[key] = value
        return parsed

    def _build_compact_editor_ui(self, parsed_data):
        # 1. Haupt prompt setzen
        if "Prompt" in parsed_data:
            self.prompt_text_edit.setPlainText(parsed_data["Prompt"])
            self.editor_widgets["Prompt"] = self.prompt_text_edit

        # 2. Vordefinierte kompakte Layout-Gruppen wie in compact.PNG
        grid_structure = [
            ['Negative Prompt'],
            ['Steps', 'CFG scale', 'Sharpness', 'Seed', 'Size'],
            ['Model', 'Model hash', 'ADM Guidance', 'Clip skip'],
            ['Lora hashes', 'Lora weights'],
            ['Sampler', 'Scheduler', 'VAE', 'Performance', 'Version']
        ]

        processed_keys = {'Prompt'}

        for row_group in grid_structure:
            # Filtere nur Schlüssel heraus, die tatsächlich Daten enthalten
            valid_keys = [k for k in row_group if k in parsed_data and parsed_data[k].strip()]
            if not valid_keys:
                continue

            for k in valid_keys:
                processed_keys.add(k)

            # Tabellenartige horizontale Reihe mit gemeinsamen Feldern
            row_box = QWidget()
            row_box.setProperty("class", "CompactCell")
            row_layout = QHBoxLayout(row_box)
            row_layout.setContentsMargins(1, 1, 1, 1)
            row_layout.setSpacing(2)

            for key in valid_keys:
                val = parsed_data[key]
                cell = QWidget()
                cell_layout = QVBoxLayout(cell)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setSpacing(1)

                lbl = QLabel(key)
                lbl.setProperty("class", "CompactHeader")
                cell_layout.addWidget(lbl)

                if len(val) > 60 or '\n' in val or key in ['Negative Prompt', 'Lora hashes', 'Lora weights', 'Raw prompt']:
                    input_w = QTextEdit(val)
                    input_w.setMinimumHeight(45)
                else:
                    input_w = QLineEdit(val)

                cell_layout.addWidget(input_w)
                row_layout.addWidget(cell)
                self.editor_widgets[key] = input_w

            self.compact_container_layout.addWidget(row_box)

        # 3. Weitere/Verbleibende Parameter auflisten
        other_keys = [k for k in parsed_data.keys() if k not in processed_keys and parsed_data[k].strip()]
        if other_keys:
            other_group = QGroupBox("Weitere Parameter")
            other_layout = QFormLayout(other_group)
            other_layout.setContentsMargins(4, 4, 4, 4)
            other_layout.setSpacing(3)

            for key in other_keys:
                val = parsed_data[key]
                if len(val) > 60 or '\n' in val:
                    input_w = QTextEdit(val)
                    input_w.setMinimumHeight(40)
                else:
                    input_w = QLineEdit(val)

                other_layout.addRow(QLabel(f"{key}:"), input_w)
                self.editor_widgets[key] = input_w

            self.compact_container_layout.addWidget(other_group)

    def save_editor_changes(self):
        if not self.current_editor_file:
            self.statusBar.showMessage("Keine Datei zum Speichern geladen.")
            return
        try:
            prompt_val = self.prompt_text_edit.toPlainText()
            neg_prompt_val = ""

            if "Negative Prompt" in self.editor_widgets:
                w = self.editor_widgets["Negative Prompt"]
                neg_prompt_val = w.toPlainText() if isinstance(w, QTextEdit) else w.text()

            new_meta_string = f"{prompt_val}\nNegative prompt: {neg_prompt_val}"
            other_params = []
            for key, widget in self.editor_widgets.items():
                if key not in ["Prompt", "Negative Prompt"]:
                    value = widget.toPlainText() if isinstance(widget, QTextEdit) else widget.text()
                    if ',' in value and not (value.startswith('"') and value.endswith('"')):
                        value = f'"{value}"'
                    other_params.append(f'{key}: {value}')
            if other_params:
                new_meta_string += "\n" + ", ".join(other_params)

            if self.current_editor_file.lower().endswith('.png'):
                img = Image.open(self.current_editor_file)
                png_info = PngImagePlugin.PngInfo()
                for key, value in img.info.items():
                    if key != 'parameters':
                        png_info.add_text(key, value)
                png_info.add_text('parameters', new_meta_string)
                img.save(self.current_editor_file, "png", pnginfo=png_info)
            elif self.current_editor_file.lower().endswith(('.jpg', '.jpeg')):
                img = Image.open(self.current_editor_file)
                exif_dict = {'Exif': {piexif.ExifIFD.UserComment: piexif.helper.UserComment.dump(new_meta_string, encoding="unicode")}}
                exif_bytes = piexif.dump(exif_dict)
                img.save(self.current_editor_file, "jpeg", exif=exif_bytes)

            self.statusBar.showMessage(f"Änderungen in '{os.path.basename(self.current_editor_file)}' gespeichert.")
        except Exception as e:
            self.statusBar.showMessage(f"Fehler beim Speichern: {e}")

    def handle_table_cell_click(self, row, column):
        filename_item = self.result_table.item(row, 0)
        if not filename_item:
            return
        full_path = filename_item.toolTip()
        if column == 0:
            pixmap = QPixmap(full_path)
            if pixmap.isNull():
                self.image_preview_label.setText("Vorschau konnte nicht geladen werden.")
                self.image_preview_label.setPixmap(QPixmap())
            else:
                self.image_preview_label.setPixmap(pixmap)
            self.display_stack.setCurrentWidget(self.image_preview_label)
        elif column == 1:
            if full_path in self.file_data_store:
                data = self.file_data_store[full_path]
                original_meta = data.get("original_meta", "")
                changed_strings = data.get("changed_strings", [])
                if not original_meta or original_meta == "N/A (Binär-Modus)":
                    display_text = "(Keine Vorschau im Binär-Modus oder keine Metadaten gefunden)"
                else:
                    display_text = original_meta.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    for s in changed_strings:
                        s_escaped = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        highlight = f'<span style="background-color:{CONFIG["colors"]["highlight_background"]};color:{CONFIG["colors"]["highlight_text"]};font-weight:bold;">{s_escaped}</span>'
                        display_text = display_text.replace(s_escaped, highlight)
                self.meta_display.setHtml(display_text.replace("\n", "<br>"))
            else:
                self.meta_display.setText("(Datei wurde noch nicht verarbeitet)")
            self.display_stack.setCurrentWidget(self.meta_display)

    def handle_table_double_click(self, item):
        file_path = self.result_table.item(item.row(), 0).toolTip()
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            self.tabs.setCurrentWidget(self.tab2)
            folder = os.path.dirname(file_path)
            self.load_directory_in_editor_list(folder)
            for i in range(self.thumb_list.count()):
                if self.thumb_list.item(i).data(Qt.ItemDataRole.UserRole) == file_path:
                    self.thumb_list.setCurrentItem(self.thumb_list.item(i))
                    break

    def toggle_mode(self):
        is_remove_mode = self.remove_radio.isChecked()
        self.remove_group.setVisible(is_remove_mode)
        self.replace_group.setVisible(not is_remove_mode)
        header_labels = ["Dateiname", "Geänderte Begriffe", "Status"] if is_remove_mode else ["Dateiname", "Ersetzter Begriff", "Status"]
        self.result_table.setHorizontalHeaderLabels(header_labels)

    def start_stop_processing(self):
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.thread.stop()
            self.start_stop_btn.setText("Start")
            return
        if not hasattr(self, 'file_paths') or not self.file_paths:
            self.statusBar.showMessage("Fehler: Bitte wählen Sie zuerst Dateien aus.")
            return
        files_to_process = {self.result_table.item(row, 0).toolTip(): row for row in range(self.result_table.rowCount())}
        settings = {
            "mode": "remove" if self.remove_radio.isChecked() else "replace",
            "terms_to_remove": self.terms_input.toPlainText(),
            "search_term": self.search_input.text(),
            "replace_term": self.replace_input.text(),
            "use_reference_file": self.ref_file_checkbox.isChecked(),
            "overwrite": self.overwrite_checkbox.isChecked(),
        }
        self.thread = ProcessingThread(files_to_process, settings)
        self.thread.progress.connect(self.statusBar.showMessage)
        self.thread.file_finished.connect(self.update_result_in_table)
        self.thread.all_finished.connect(self.on_processing_finished)
        self.thread.start()
        self.start_stop_btn.setText("Abbrechen")

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Bilder auswählen", self.current_editor_dir, "Bilddateien (*.png *.jpg *.jpeg)")
        if files:
            self.file_paths = files
            self.current_editor_dir = os.path.dirname(files[0])
            tooltip_text = "\n".join([os.path.basename(f) for f in self.file_paths])
            self.selected_files_label.setText(f"{len(files)} Datei(en) ausgewählt.")
            self.selected_files_label.setToolTip(tooltip_text)
            self.populate_table_with_files()

    def populate_table_with_files(self):
        self.result_table.setRowCount(len(self.file_paths))
        self.file_data_store.clear()
        self.meta_display.clear()
        for row, file_path in enumerate(self.file_paths):
            item_filename = QTableWidgetItem(os.path.basename(file_path))
            item_filename.setToolTip(file_path)
            self.result_table.setItem(row, 0, item_filename)
            self.result_table.setItem(row, 1, QTableWidgetItem(""))
            self.result_table.setItem(row, 2, QTableWidgetItem(""))

    def update_result_in_table(self, result):
        row, file_path = result["row"], result["file_path"]
        self.file_data_store[file_path] = {"original_meta": result.get("original_meta", ""), "changed_strings": result.get("changed_strings", [])}
        changed_str = ", ".join(result.get("changed_strings", []))
        item_changed = QTableWidgetItem(changed_str)
        item_status = QTableWidgetItem(result.get("status", "Unbekannt"))
        item_changed.setToolTip(changed_str)
        item_status.setToolTip(result.get("status", "Unbekannt"))
        self.result_table.setItem(row, 1, item_changed)
        self.result_table.setItem(row, 2, item_status)

    def on_processing_finished(self, summary):
        self.statusBar.showMessage(summary)
        self.start_stop_btn.setText("Start")
        self.thread = None

    def closeEvent(self, event):
        """Speichert Position, Splitter-Größen und Thumbnail-Einstellungen in <script>.ini."""
        settings = QSettings(INI_PATH, QSettings.Format.IniFormat)
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("last_directory", self.current_editor_dir)

        # Thumbnail Einstellungen speichern
        settings.setValue("thumb_port_w", self.spin_port_w.value())
        settings.setValue("thumb_port_h", self.spin_port_h.value())
        settings.setValue("thumb_land_w", self.spin_land_w.value())
        settings.setValue("thumb_land_h", self.spin_land_h.value())

        # Highlight Farben und Historie speichern
        settings.setValue("prompt_highlight_bg", self.prompt_highlight_bg)
        settings.setValue("prompt_highlight_fg", self.prompt_highlight_fg)
        settings.setValue("prompt_highlight_history", self.prompt_highlight_history)

        # Splitter-Größen speichern
        settings.setValue("tab1_main_splitter", self.tab1_main_splitter.saveState())
        settings.setValue("tab1_result_splitter", self.tab1_result_splitter.saveState())
        settings.setValue("tab2_main_splitter", self.tab2_main_splitter.saveState())
        settings.setValue("editor_splitter", self.editor_splitter.saveState())

        super().closeEvent(event)

    def load_settings(self):
        """Lädt Einstellungen beim Start aus <script>.ini."""
        if not os.path.exists(INI_PATH):
            return
        settings = QSettings(INI_PATH, QSettings.Format.IniFormat)
        
        if settings.value("geometry"):
            self.restoreGeometry(settings.value("geometry"))
        if settings.value("windowState"):
            self.restoreState(settings.value("windowState"))

        # Thumbnail Einstellungen laden
        self.thumb_portrait_w = int(settings.value("thumb_port_w", 200))
        self.thumb_portrait_h = int(settings.value("thumb_port_h", 300))
        self.thumb_landscape_w = int(settings.value("thumb_land_w", 300))
        self.thumb_landscape_h = int(settings.value("thumb_land_h", 200))

        # Highlight Farben und Historie laden
        self.prompt_highlight_bg = str(settings.value("prompt_highlight_bg", "#8B0000"))
        self.prompt_highlight_fg = str(settings.value("prompt_highlight_fg", "#ffffff"))

        history = settings.value("prompt_highlight_history")
        if isinstance(history, list):
            self.prompt_highlight_history = [str(item) for item in history if item][:15]
        else:
            self.prompt_highlight_history = []

        if hasattr(self, 'prompt_highlight_input') and isinstance(self.prompt_highlight_input, QComboBox):
            self.prompt_highlight_input.blockSignals(True)
            self.prompt_highlight_input.clear()
            self.prompt_highlight_input.addItems(self.prompt_highlight_history)
            self.prompt_highlight_input.blockSignals(False)

        self.spin_port_w.setValue(self.thumb_portrait_w)
        self.spin_port_h.setValue(self.thumb_portrait_h)
        self.spin_land_w.setValue(self.thumb_landscape_w)
        self.spin_land_h.setValue(self.thumb_landscape_h)
            
        last_dir = settings.value("last_directory")
        if last_dir and os.path.exists(last_dir):
            self.current_editor_dir = last_dir
            self.load_directory_in_editor_list(last_dir)

        if settings.value("tab1_main_splitter"):
            self.tab1_main_splitter.restoreState(settings.value("tab1_main_splitter"))
        if settings.value("tab1_result_splitter"):
            self.tab1_result_splitter.restoreState(settings.value("tab1_result_splitter"))
        if settings.value("tab2_main_splitter"):
            self.tab2_main_splitter.restoreState(settings.value("tab2_main_splitter"))
        if settings.value("editor_splitter"):
            self.editor_splitter.restoreState(settings.value("editor_splitter"))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ExifEditorApp()
    ex.show()
    sys.exit(app.exec())