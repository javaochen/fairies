import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

import fitz  # PyMuPDF
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# =========================
# 配置区
# =========================
PDF_ROOT_DIR = r"C:\Users\32475\Downloads"
INITIAL_PDF_KEYWORD = ""
INITIAL_PAGE = 1
HISTORY_FILE_NAME = ".pdf_reader_history.json"


@dataclass
class PdfEntry:
    name: str
    path: str


class HistoryStore:
    def __init__(self, root_dir: str, file_name: str = HISTORY_FILE_NAME):
        self.root_dir = root_dir
        self.path = os.path.join(root_dir, file_name)
        self.data: Dict[str, int] = {}
        self.load()

    def load(self):
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                    if isinstance(obj, dict):
                        self.data = {str(k): int(v) for k, v in obj.items()}
        except Exception:
            self.data = {}

    def save(self):
        try:
            os.makedirs(self.root_dir, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def record_open(self, filename: str):
        self.data[filename] = self.data.get(filename, 0) + 1
        self.save()

    def count(self, filename: str) -> int:
        return self.data.get(filename, 0)


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用说明")
        self.resize(700, 500)

        layout = QVBoxLayout(self)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "PDF 阅读器使用说明\n"
            "================\n\n"
            "1. 快速切换 PDF\n"
            "   - 点击顶部“快速切换 PDF”按钮\n"
            "   - 或按 Ctrl+P\n"
            "   - 输入部分文件名即可筛选\n"
            "   - 单击列表项即可打开\n\n"
            "2. 翻页\n"
            "   - 左方向键：上一页\n"
            "   - 右方向键：下一页\n\n"
            "3. 跳页\n"
            "   - 点击“跳页 Ctrl+I”按钮\n"
            "   - 或按 Ctrl+I\n"
            "   - 输入页码后确认\n\n"
            "4. 缩放\n"
            "   - 点击“放大”或“缩小”按钮\n"
            "   - 或使用 Ctrl+= / Ctrl+-\n"
            "   - 也可按住 Ctrl 后滚轮缩放\n\n"
            "5. 书签\n"
            "   - 点击“书签”按钮显示/隐藏书签栏\n"
            "   - 书签默认展开全部层级\n"
            "   - 单击任意书签可跳转到对应页\n\n"
            "6. 打开历史\n"
            "   - 保存在 PDF 根目录下的 .pdf_reader_history.json\n"
            "   - 仅记录文件名及打开次数\n"
            "   - 快速切换时会按历史次数优先排序\n\n"
            "7. 根目录\n"
            f"   - 当前扫描目录：{PDF_ROOT_DIR}\n"
        )
        layout.addWidget(text)

        btn_row = QHBoxLayout()
        close_btn = QPushButton("关闭")
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        close_btn.clicked.connect(self.accept)


class QuickSwitchDialog(QDialog):
    def __init__(self, pdf_list: List[PdfEntry], history: HistoryStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快速切换 PDF")
        self.resize(800, 520)
        self.pdf_list = pdf_list
        self.history = history
        self.selected_path: Optional[str] = None

        layout = QVBoxLayout(self)

        self.input = QLineEdit()
        self.input.setPlaceholderText("输入部分文件名，例如 math / report / chapter")
        layout.addWidget(self.input)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        self.open_btn = QPushButton("打开")
        self.cancel_btn = QPushButton("取消")
        btn_row.addStretch(1)
        btn_row.addWidget(self.open_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self.input.textChanged.connect(self.update_list)
        self.list_widget.itemClicked.connect(self.accept_selection)
        self.list_widget.itemDoubleClicked.connect(self.accept_selection)
        self.open_btn.clicked.connect(self.accept_selection)
        self.cancel_btn.clicked.connect(self.reject)
        self.input.returnPressed.connect(self.accept_selection)

        self.update_list("")
        self.input.setFocus()

    def update_list(self, text: str):
        self.list_widget.clear()
        q = text.strip().lower()

        items = []
        for entry in self.pdf_list:
            name_l = entry.name.lower()
            if not q or q in name_l:
                history_count = self.history.count(entry.name)
                prefix_score = 0 if name_l.startswith(q) else 1
                # 先按历史次数降序，再按前缀优先，再按文件名
                items.append((-history_count, prefix_score, entry.name, entry.path))

        items.sort(key=lambda x: (x[0], x[1], x[2].lower()))

        for neg_count, _, name, path in items[:300]:
            count = -neg_count
            display = f"{name}   [历史打开 {count} 次]" if count > 0 else name
            item = QListWidgetItem(display)
            item.setToolTip(path)
            item.setData(Qt.UserRole, path)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def accept_selection(self):
        item = self.list_widget.currentItem()
        if item:
            self.selected_path = item.data(Qt.UserRole)
            self.accept()


class JumpPageDialog(QDialog):
    def __init__(self, total_pages: int, current_page: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("跳页")
        self.resize(320, 120)
        self.page: Optional[int] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"请输入页码（1 - {total_pages}）："))

        self.spin = QSpinBox()
        self.spin.setRange(1, max(1, total_pages))
        self.spin.setValue(max(1, current_page))
        layout.addWidget(self.spin)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        btn_row.addStretch(1)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        ok_btn.clicked.connect(self.accept_page)
        cancel_btn.clicked.connect(self.reject)

    def accept_page(self):
        self.page = self.spin.value()
        self.accept()


class BookmarkPanel(QWidget):
    def __init__(self, on_jump_to_page, parent=None):
        super().__init__(parent)
        self.on_jump_to_page = on_jump_to_page

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        title = QLabel("书签（展开全部层级）")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(self.handle_click)
        self.tree.itemDoubleClicked.connect(self.handle_click)
        layout.addWidget(self.tree, 1)

    def load_bookmarks(self, toc):
        self.tree.clear()
        if not toc:
            item = QTreeWidgetItem(["无书签"])
            self.tree.addTopLevelItem(item)
            return

        stack = []
        for level, title, page, _ in toc:
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.UserRole, page)

            while stack and stack[-1][0] >= level:
                stack.pop()

            if not stack:
                self.tree.addTopLevelItem(item)
            else:
                stack[-1][1].addChild(item)

            stack.append((level, item))

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)

    def handle_click(self, item, column):
        page = item.data(0, Qt.UserRole)
        if page:
            self.on_jump_to_page(page)


class PdfViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Optional[fitz.Document] = None
        self.current_path: Optional[str] = None
        self.current_page_index = 0
        self.zoom = 1.6
        self.page_cache = {}
        self.render_id = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel("请打开一个 PDF")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #202020; color: white;")
        self.image_label.setMinimumSize(800, 600)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.image_label)

        layout.addWidget(self.scroll)

    def close_pdf(self):
        self.render_id += 1
        self.page_cache.clear()
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = None
        self.current_path = None
        self.current_page_index = 0
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("请打开一个 PDF")

    def open_pdf(self, path: str, page_1_based: int = 1):
        self.close_pdf()
        try:
            self.doc = fitz.open(path)
            self.current_path = path
            self.goto_page(page_1_based)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法打开 PDF：\n{path}\n\n{e}")
            self.close_pdf()

    def total_pages(self) -> int:
        return self.doc.page_count if self.doc else 0

    def current_page_1_based(self) -> int:
        return self.current_page_index + 1

    def goto_page(self, page_1_based: int):
        if not self.doc:
            return
        page_1_based = max(1, min(page_1_based, self.doc.page_count))
        self.current_page_index = page_1_based - 1
        self.render_current_page()

    def next_page(self):
        if self.doc and self.current_page_index < self.doc.page_count - 1:
            self.current_page_index += 1
            self.render_current_page()

    def prev_page(self):
        if self.doc and self.current_page_index > 0:
            self.current_page_index -= 1
            self.render_current_page()

    def zoom_in(self):
        self.zoom = min(4.0, self.zoom + 0.1)
        self.page_cache.clear()
        self.render_current_page()

    def zoom_out(self):
        self.zoom = max(0.5, self.zoom - 0.1)
        self.page_cache.clear()
        self.render_current_page()

    def render_current_page(self):
        if not self.doc:
            return

        key = (self.current_path, self.current_page_index, self.zoom)
        self.render_id += 1
        current_render_id = self.render_id

        if key in self.page_cache:
            self.image_label.setPixmap(self.page_cache[key])
            self.image_label.adjustSize()
            return

        try:
            page = self.doc.load_page(self.current_page_index)
            mat = fitz.Matrix(self.zoom, self.zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            img_format = QImage.Format_RGB888 if pix.n < 4 else QImage.Format_RGBA8888
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, img_format).copy()

            if current_render_id != self.render_id:
                return

            pixmap = QPixmap.fromImage(qimg)
            self.page_cache[key] = pixmap
            self.image_label.setPixmap(pixmap)
            self.image_label.adjustSize()
        except Exception as e:
            self.image_label.setText(f"渲染失败：{e}")

    def load_bookmarks(self):
        if not self.doc:
            return []
        try:
            return self.doc.get_toc(simple=False)
        except Exception:
            return []

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python PDF Reader")
        self.resize(1200, 900)

        self.history = HistoryStore(PDF_ROOT_DIR)
        self.pdf_entries: List[PdfEntry] = self.scan_pdf_files(PDF_ROOT_DIR)

        self.viewer = PdfViewer()
        self.bookmark_panel = BookmarkPanel(self.jump_to_page)

        self.splitter = QSplitter()
        self.splitter.addWidget(self.bookmark_panel)
        self.splitter.addWidget(self.viewer)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setSizes([320, 880])

        self.status = self.statusBar()
        self.status.showMessage(f"已扫描 {len(self.pdf_entries)} 个 PDF")

        self._build_ui()
        self._setup_shortcuts()

        if INITIAL_PDF_KEYWORD:
            path = self.pick_pdf_by_keyword(INITIAL_PDF_KEYWORD)
            if path:
                self.open_pdf(path, INITIAL_PAGE)
        elif self.pdf_entries:
            self.open_pdf(self.pdf_entries[0].path, INITIAL_PAGE)

    def scan_pdf_files(self, root_dir: str) -> List[PdfEntry]:
        entries = []
        if not os.path.isdir(root_dir):
            return entries
        for base, _, files in os.walk(root_dir):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    entries.append(PdfEntry(name=fn, path=os.path.join(base, fn)))
        entries.sort(key=lambda x: x.name.lower())
        return entries

    def pick_pdf_by_keyword(self, keyword: str) -> Optional[str]:
        q = keyword.lower().strip()
        matches = [e for e in self.pdf_entries if q in e.name.lower()]
        if not matches:
            return None
        matches.sort(key=lambda e: (0 if e.name.lower().startswith(q) else 1, e.name.lower()))
        return matches[0].path

    def _build_ui(self):
        top_bar = QWidget()
        row = QHBoxLayout(top_bar)
        row.setContentsMargins(6, 6, 6, 6)

        self.btn_quick_switch = QPushButton("快速切换 PDF")
        self.btn_open = QPushButton("打开 PDF")
        self.btn_jump = QPushButton("跳页 Ctrl+I")
        self.btn_bookmarks = QPushButton("书签")
        self.btn_zoom_in = QPushButton("放大")
        self.btn_zoom_out = QPushButton("缩小")
        self.btn_help = QPushButton("使用说明")

        self.btn_quick_switch.clicked.connect(self.quick_switch_dialog)
        self.btn_open.clicked.connect(self.open_dialog)
        self.btn_jump.clicked.connect(self.jump_dialog)
        self.btn_bookmarks.clicked.connect(self.toggle_bookmark_panel)
        self.btn_zoom_in.clicked.connect(self.viewer.zoom_in)
        self.btn_zoom_out.clicked.connect(self.viewer.zoom_out)
        self.btn_help.clicked.connect(self.show_help)

        row.addWidget(self.btn_quick_switch)
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_jump)
        row.addWidget(self.btn_bookmarks)
        row.addWidget(self.btn_zoom_in)
        row.addWidget(self.btn_zoom_out)
        row.addWidget(self.btn_help)
        row.addStretch(1)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(top_bar)
        main_layout.addWidget(self.splitter, 1)
        self.setCentralWidget(container)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self.viewer.prev_page)
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self.viewer.next_page)
        QShortcut(QKeySequence("Ctrl+I"), self, activated=self.jump_dialog)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.quick_switch_dialog)
        QShortcut(QKeySequence("Home"), self, activated=lambda: self.jump_to_page(1))
        QShortcut(QKeySequence("End"), self, activated=self.jump_to_last_page)
        QShortcut(QKeySequence("Ctrl+-"), self, activated=self.viewer.zoom_out)
        QShortcut(QKeySequence("Ctrl+="), self, activated=self.viewer.zoom_in)

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 PDF", PDF_ROOT_DIR, "PDF Files (*.pdf)")
        if path:
            self.open_pdf(path, 1)

    def show_help(self):
        dlg = HelpDialog(self)
        dlg.exec()

    def quick_switch_dialog(self):
        dlg = QuickSwitchDialog(self.pdf_entries, self.history, self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_path:
            self.open_pdf(dlg.selected_path, 1)

    def jump_dialog(self):
        total = self.viewer.total_pages()
        if total <= 0:
            return
        dlg = JumpPageDialog(total, self.viewer.current_page_1_based(), self)
        if dlg.exec() == QDialog.Accepted and dlg.page:
            self.jump_to_page(dlg.page)

    def open_pdf(self, path: str, page_1_based: int = 1):
        self.viewer.open_pdf(path, page_1_based)
        self.refresh_bookmarks()
        if self.viewer.current_path:
            self.history.record_open(os.path.basename(path))
        self.status.showMessage(f"已打开：{os.path.basename(path)} | 第 {page_1_based} 页")

    def jump_to_page(self, page_1_based: int):
        self.viewer.goto_page(page_1_based)
        if self.viewer.current_path:
            self.status.showMessage(
                f"{os.path.basename(self.viewer.current_path)} | 第 {self.viewer.current_page_1_based()} / {self.viewer.total_pages()} 页 | 缩放 {self.viewer.zoom:.1f}x"
            )

    def jump_to_last_page(self):
        total = self.viewer.total_pages()
        if total > 0:
            self.jump_to_page(total)

    def refresh_bookmarks(self):
        toc = self.viewer.load_bookmarks()
        self.bookmark_panel.load_bookmarks(toc)

    def toggle_bookmark_panel(self):
        self.bookmark_panel.setVisible(not self.bookmark_panel.isVisible())
        if self.bookmark_panel.isVisible():
            self.refresh_bookmarks()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()