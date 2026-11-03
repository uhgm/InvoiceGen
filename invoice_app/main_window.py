# -*- coding: utf-8 -*-
"""
請求書かんたん作成ツールの画面（Qt / PySide6 版）。

起動は invoice_generator.py から行う（PySide6 が入っているかを先に確認するため）。
PDFの描画は pdf_builder.py、アップデートは updater.py がそれぞれ担当していて、
このファイルは「入力画面」と「プレビュー」だけを受け持つ。
"""
import datetime
import html
import os
import sys
import traceback
from io import BytesIO

from PySide6.QtCore import QDate, QLibraryInfo, QLocale, QTimer, QTranslator, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QCompleter, QDateEdit,
    QDialog, QFileDialog, QFormLayout, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QSplitterHandle, QTableWidget, QTableWidgetItem,
    QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

import app_common as common
from app_common import (
    APP_CREDIT, APP_DIR, APP_SUPPORT_EMAIL, APP_VERSION, APP_VERSION_NUM, DOC_FORMAT_LABELS,
    DUMMY_BANKS, DUMMY_BUTTON_CLEAR, DUMMY_BUTTON_FILL, DUMMY_FIELDS, DUMMY_ITEMS, DUMMY_REMARKS,
    DUMMY_SEAL_PATH, DUMMY_STATUS_ACTIVE, DUMMY_STATUS_IDLE, HELP_TEXT, MAX_DESTINATION_HISTORY,
    UPDATE_MANIFEST_URL, format_yen, load_config, normalize_number, parse_number, safe_filename,
    save_config, to_reiwa,
)

try:
    # PDFプレビュー表示用（PDFのページを画像に変換するライブラリ）。
    # 入っていなくてもアプリ自体は問題なく動くようにしておく。
    import pymupdf as fitz  # PyMuPDF（新しいバージョンでの推奨インポート名）
    PDF_PREVIEW_AVAILABLE = True
except Exception:
    try:
        import fitz  # PyMuPDF（古いバージョン向けのインポート名）
        PDF_PREVIEW_AVAILABLE = True
    except Exception:
        fitz = None
        PDF_PREVIEW_AVAILABLE = False

# ------------------------------------------------------------------
# 配色
# ------------------------------------------------------------------
# PDF側（pdf_builder.py）と同じく、請求書＝青、領収証＝緑、一括作成＝紫。
ACCENT = "#2f6fed"
COLOR_INVOICE = "#2f6fed"
COLOR_RECEIPT = "#1e9e5a"
COLOR_BOTH = "#6b4fd8"
COLOR_TOTAL = "#c62f2f"

# 表のセルに付ける目印（ダミーデータで入れた値／ダミーのために増やした行）
DUMMY_ROLE = Qt.UserRole + 1
DUMMY_ADDED_ROLE = Qt.UserRole + 2
DUMMY_PROP = "dummy_value"


def _style_sheet(arrow_icon_path):
    arrow = arrow_icon_path.replace("\\", "/")
    return f"""
QWidget {{ color: #1f2933; }}
QMainWindow, #Central {{ background: #f3f5f9; }}
#FormArea {{ background: transparent; }}

#Header {{ background: #ffffff; border-bottom: 1px solid #e3e8ef; }}
#AppTitle {{ font-size: 15pt; font-weight: bold; }}
#VersionChip {{ background: #eef3fd; color: {ACCENT}; border-radius: 9px; padding: 2px 10px; font-size: 9pt; }}
#FormatBox {{ background: #eef3fd; border: 1px solid #b9cdf7; border-radius: 10px; }}
#FormatLabel {{ color: {ACCENT}; font-weight: bold; font-size: 12pt; }}
#FormatCombo {{ font-size: 12pt; font-weight: bold; }}
#FormatChip {{ background: #ffffff; color: {ACCENT}; border: 1px solid #b9cdf7; border-radius: 9px; padding: 2px 10px; }}

#Card {{ background: #ffffff; border: 1px solid #e3e8ef; border-radius: 12px; }}
#CardTitle {{ font-size: 13pt; font-weight: bold; }}
#CardHelp, #Hint {{ color: #6b7685; }}
#DummyBar {{ background: #fff8e6; border: 1px dashed #e9b949; border-radius: 12px; }}
#DummyStatus {{ color: #8a6d1d; }}
#DummyStatus[active="true"] {{ color: #c62f2f; font-weight: bold; }}

QLineEdit, QComboBox, QDateEdit, QPlainTextEdit {{
    background: #ffffff; border: 1px solid #cfd6e0; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {{ border: 2px solid {ACCENT}; padding: 4px 7px; }}
QLineEdit:disabled, QDateEdit:disabled {{ background: #f1f3f6; color: #9aa4b2; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{arrow}"); width: 12px; height: 12px; }}
/* 一覧は必ずドロップダウンの真下に開く（Fusionの既定だと「選択中の項目が重なる位置」に開き、
   画面のいちばん上にあるドロップダウンでは上の項目が画面の外に切れてしまう） */
QComboBox {{ combobox-popup: 0; }}
QComboBox QAbstractItemView {{ border: 1px solid #cfd6e0; selection-background-color: #eef3fd; selection-color: #1f2933; }}

QPushButton {{ background: #ffffff; border: 1px solid #cfd6e0; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: #eef3fd; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #dde7fb; }}
QPushButton:checked {{ background: {ACCENT}; color: #ffffff; border-color: {ACCENT}; }}
#HeaderButton {{ border: none; background: transparent; color: #4a5565; }}
#HeaderButton:hover {{ background: #eef3fd; color: {ACCENT}; }}
#DummyButton {{ background: #ffffff; border-color: #e9b949; }}
#DummyButton:hover {{ background: #fff1cc; border-color: #d39e1f; }}

#PrimaryInvoice, #PrimaryReceipt, #PrimaryBoth {{
    color: #ffffff; border: none; border-radius: 10px; padding: 14px 10px;
    font-size: 13pt; font-weight: bold;
}}
#PrimaryInvoice {{ background: {COLOR_INVOICE}; }}
#PrimaryInvoice:hover {{ background: #255bd0; }}
#PrimaryReceipt {{ background: {COLOR_RECEIPT}; }}
#PrimaryReceipt:hover {{ background: #18834a; }}
#PrimaryBoth {{ background: {COLOR_BOTH}; }}
#PrimaryBoth:hover {{ background: #5939c2; }}

QTableWidget {{
    font-size: 11pt; background: #ffffff; border: 1px solid #e3e8ef; border-radius: 8px;
    gridline-color: #edf0f5; selection-background-color: #eef3fd; selection-color: #1f2933;
}}
QTableWidget QLineEdit {{ border: none; border-radius: 0; padding: 0 6px; }}
QHeaderView::section {{
    background: #f6f8fb; border: none; border-bottom: 1px solid #e3e8ef;
    padding: 6px; font-weight: bold; color: #4a5565;
}}
#RowDelete {{ border: none; background: transparent; color: #9aa4b2; font-size: 12pt; }}
#RowDelete:hover {{ color: #c62f2f; }}
#TotalLabel {{ color: #4a5565; font-weight: bold; font-size: 12pt; }}
#TotalValue {{ color: {COLOR_TOTAL}; font-weight: bold; font-size: 17pt; }}

#SealThumb {{ background: #f6f8fb; border: 1px dashed #cfd6e0; border-radius: 8px; color: #9aa4b2; }}

#PreviewPanel {{ background: #e9edf3; }}
#PreviewTitle {{ font-size: 13pt; font-weight: bold; }}
#PreviewScroll {{ background: transparent; border: none; }}
#PreviewPage {{ background: #ffffff; color: #9aa4b2; }}
#Segment {{ padding: 5px 18px; }}

#ActionBar {{ background: #ffffff; border-top: 1px solid #e3e8ef; }}
#ActionCaption {{ color: #6b7685; font-size: 9pt; }}
#Footer {{ color: #9aa4b2; font-size: 9pt; }}

QSplitter::handle {{ background: #dde2ea; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}
QScrollArea {{ border: none; }}
"""


def _write_arrow_icon():
    """入力欄の▼（ドロップダウンの矢印）用の小さなSVG画像を作る。
    見た目を整えるとQtの標準の矢印が消えるため、代わりの画像を用意している。"""
    path = os.path.join(common.USER_DATA_DIR, "ui_arrow_down.svg")
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
           '<path d="M2 4 L6 8 L10 4" fill="none" stroke="#4a5565" stroke-width="1.8" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
    except Exception:
        pass
    return path


def wrapped_label(text, object_name="CardHelp"):
    """折り返して複数行になる説明文のラベル。

    画面の書体（BIZ UDPGothic）は行間の情報が 0 のため、そのままだと
    2行目が1行目にくっついて文字が重なって見える。そこで行間を広げて表示する。"""
    label = QLabel(objectName=object_name)
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(True)
    set_wrapped_text(label, text)
    return label


def set_wrapped_text(label, text):
    body = html.escape(text).replace("\n", "<br>")
    label.setText(f'<div style="line-height:145%;">{body}</div>')


# ------------------------------------------------------------------
# メッセージ（ボタンの文字を日本語にするため、自前で組み立てる）
# ------------------------------------------------------------------
def _message(parent, icon, title, text, buttons):
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    created = [box.addButton(label, role) for label, role in buttons]
    box.setDefaultButton(created[0])
    box.exec()
    clicked = box.clickedButton()
    return created.index(clicked) if clicked in created else -1


def show_info(parent, title, text):
    _message(parent, QMessageBox.Information, title, text, [("OK", QMessageBox.AcceptRole)])


def show_warning(parent, title, text):
    _message(parent, QMessageBox.Warning, title, text, [("OK", QMessageBox.AcceptRole)])


def show_error(parent, title, text):
    _message(parent, QMessageBox.Critical, title, text, [("OK", QMessageBox.AcceptRole)])


def ask_yes_no(parent, title, text):
    buttons = [("はい", QMessageBox.YesRole), ("いいえ", QMessageBox.NoRole)]
    return _message(parent, QMessageBox.Question, title, text, buttons) == 0


# ------------------------------------------------------------------
# 入力用の表（品目・振込先）
# ------------------------------------------------------------------
class InputTable(QTableWidget):
    """品目・振込先の入力表。いちばん右の列に、行を消す「✕」ボタンを置く。

    columns は (見出し, 幅, 寄せ方) のリスト。幅が None の列は残りの幅いっぱいに広がる。
    computed_col を指定すると、その列は入力できない自動計算の列になり、
    compute(行の値のリスト) の戻り値が表示される（品目の「金額」）。
    """

    changed = Signal()

    def __init__(self, columns, defaults, blank_check_cols, computed_col=None, compute=None, parent=None):
        super().__init__(0, len(columns) + 1, parent)
        self.ncols = len(columns)
        self.defaults = defaults
        self.blank_check_cols = blank_check_cols
        self.computed_col = computed_col
        self.compute = compute
        self.aligns = [align for _, _, align in columns]

        self.setHorizontalHeaderLabels([title for title, _, _ in columns] + [""])
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        for col, (_, width, _) in enumerate(columns):
            if width is None:
                header.setSectionResizeMode(col, QHeaderView.Stretch)
            else:
                header.setSectionResizeMode(col, QHeaderView.Fixed)
                self.setColumnWidth(col, width)
        header.setSectionResizeMode(self.ncols, QHeaderView.Fixed)
        self.setColumnWidth(self.ncols, 40)

        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(38)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # クリックしたらすぐ入力できるようにする（ダブルクリック不要）
        self.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setWordWrap(False)
        self.itemChanged.connect(self._on_item_changed)

    # ---- 行の追加・削除 ----
    def add_row(self, values=None):
        row = self.rowCount()
        self.insertRow(row)
        self.blockSignals(True)
        for col in range(self.ncols):
            text = values[col] if values is not None and values[col] is not None else self.defaults[col]
            item = QTableWidgetItem(text)
            item.setTextAlignment(self.aligns[col] | Qt.AlignVCenter)
            if col == self.computed_col:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setBackground(QColor("#f6f8fb"))
            self.setItem(row, col, item)
        self.blockSignals(False)
        self._update_computed(row)

        btn = QToolButton(objectName="RowDelete", text="✕")
        btn.setToolTip("この行を削除します")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self._remove_row_of(btn))
        self.setCellWidget(row, self.ncols, btn)
        self.fit_height()
        self.changed.emit()
        return row

    def _remove_row_of(self, btn):
        row = self.indexAt(btn.pos()).row()
        if row < 0:
            return
        if self.rowCount() <= 1:
            self.set_row(row, self.defaults)  # 最後の1行は消さずに空にする
        else:
            self.removeRow(row)
            self.fit_height()
        self.changed.emit()

    def remove_rows(self, rows):
        for row in sorted(rows, reverse=True):
            if self.rowCount() > 1:
                self.removeRow(row)
        self.fit_height()
        self.changed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_height()  # 表示されて見出しの高さが確定してから、高さを測り直す

    def fit_height(self):
        """表の中でスクロールさせず、行数ぶんの高さをそのまま使う。"""
        height = self.horizontalHeader().sizeHint().height() + self.frameWidth() * 2
        height += sum(self.rowHeight(r) for r in range(self.rowCount()))
        self.setFixedHeight(height + 2)

    # ---- 値の読み書き ----
    def row_values(self, row):
        return [self.item(row, col).text() if self.item(row, col) else "" for col in range(self.ncols)]

    def set_row(self, row, values):
        for col in range(self.ncols):
            if col != self.computed_col and values[col] is not None:
                self.item(row, col).setText(values[col])

    def is_blank(self, row):
        values = self.row_values(row)
        return not any(values[col].strip() for col in self.blank_check_cols)

    def all_blank(self):
        return all(self.is_blank(r) for r in range(self.rowCount()))

    def _on_item_changed(self, item):
        if item.column() != self.computed_col:
            self._update_computed(item.row())
            self.changed.emit()

    def _update_computed(self, row):
        if self.computed_col is None or self.compute is None:
            return
        item = self.item(row, self.computed_col)
        if item is None:
            return
        self.blockSignals(True)
        item.setText(self.compute(self.row_values(row)))
        self.blockSignals(False)

    # ---- ダミーデータ ----
    def fill_dummy(self, rows):
        """表がまるごと空のときだけ、ダミーの行を入れる（途中の行に混ぜない）。"""
        if not self.all_blank():
            return
        while self.rowCount() < len(rows):
            row = self.add_row()
            self.item(row, 0).setData(DUMMY_ADDED_ROLE, True)
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                if value is None or col == self.computed_col:
                    continue
                item = self.item(row, col)
                item.setText(value)
                item.setData(DUMMY_ROLE, value)

    def clear_dummy(self):
        """ダミーで入れたまま書き換えられていないセルだけを、元の空の状態に戻す。"""
        for row in range(self.rowCount()):
            for col in range(self.ncols):
                item = self.item(row, col)
                value = item.data(DUMMY_ROLE) if item else None
                if value is None:
                    continue
                if item.text() == value:
                    item.setText(self.defaults[col])
                item.setData(DUMMY_ROLE, None)
        added = [r for r in range(self.rowCount())
                 if self.item(r, 0).data(DUMMY_ADDED_ROLE) and self.is_blank(r)]
        if added:
            self.remove_rows(added)


class _ResettableSplitter(QSplitter):
    """仕切りをダブルクリックすると、元の配置に戻る左右分割。"""

    def __init__(self, on_reset, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.on_reset = on_reset

    def createHandle(self):
        return _SplitterHandle(self.orientation(), self)


class _SplitterHandle(QSplitterHandle):
    def mouseDoubleClickEvent(self, event):
        self.splitter().on_reset()


# ------------------------------------------------------------------
# メイン画面
# ------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        # ダミーデータを入れている間は、設定・取引先履歴を保存しない
        # （本番の設定に「ダミー株式会社」などが混ざらないようにするため）
        self._dummy_active = False
        self._dummy_remarks = False
        self._dummy_seal = False

        self.setWindowTitle(f"請求書かんたん作成ツール - {APP_VERSION}")
        self.f = {}  # 1行入力欄（ダミーデータの項目名と同じキー）

        self._preview_timer = QTimer(self, singleShot=True, interval=500)
        self._preview_timer.timeout.connect(self._update_preview)

        central = QWidget(objectName="Central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        self.splitter = _ResettableSplitter(self._reset_pane_layout)
        self.splitter.setHandleWidth(8)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_form())
        self.splitter.addWidget(self._build_preview())
        self.splitter.splitterMoved.connect(lambda *_: self._schedule_preview())
        root.addWidget(self.splitter, 1)
        root.addWidget(self._build_action_bar())

        self._load_defaults_into_form()
        self._connect_change_signals()

    # ============================================================ 画面の組み立て
    def _build_header(self):
        bar = QFrame(objectName="Header")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 10, 16, 10)
        lay.setSpacing(10)
        lay.addWidget(QLabel("🧾 請求書かんたん作成ツール", objectName="AppTitle"))
        lay.addWidget(QLabel(APP_VERSION, objectName="VersionChip"), 0, Qt.AlignVCenter)
        lay.addStretch(1)

        # PDFの書式は請求書・領収証のどちらにも効くので、いちばん上の中央に、
        # 枠で囲んで目立つように置く。選んだ書式は設定ファイルに保存され、
        # 次回起動時も同じ書式になる。
        format_box = QFrame(objectName="FormatBox")
        format_lay = QHBoxLayout(format_box)
        format_lay.setContentsMargins(14, 6, 8, 6)
        format_lay.setSpacing(10)
        format_lay.addWidget(QLabel("📄 PDFの書式", objectName="FormatLabel"))
        self.format_combo = QComboBox(objectName="FormatCombo")
        for key, label in DOC_FORMAT_LABELS.items():
            self.format_combo.addItem(label, key)
        saved = self.cfg.get("doc_format", "standard")
        index = self.format_combo.findData(saved)
        self.format_combo.setCurrentIndex(index if index >= 0 else 0)
        self.format_combo.setMinimumWidth(190)
        self.format_combo.setToolTip(
            "「クラシック」は、これまで使っていたシステムの請求書・領収書と同じ配置で作成します\n"
            "（宛先は名前と「御中」のみ、但し書きは印字されません）。\n"
            "選んだ書式は次回からも自動的に使われます。"
        )
        self.format_combo.currentIndexChanged.connect(self._on_doc_format_changed)
        format_lay.addWidget(self.format_combo)
        lay.addWidget(format_box)
        lay.addStretch(1)

        for text, slot in (
            ("↔ 配置を元に戻す", self._reset_pane_layout),
            ("🔄 アップデート確認", self.check_for_updates),
            ("？ 使い方ヘルプ", self.show_help),
        ):
            btn = QPushButton(text, objectName="HeaderButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            lay.addWidget(btn)
        return bar

    def _build_form(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget(objectName="FormArea")
        self.form_layout = QVBoxLayout(body)
        self.form_layout.setContentsMargins(20, 18, 16, 24)
        self.form_layout.setSpacing(14)
        scroll.setWidget(body)

        # ---- 出力テスト用：ダミーデータ ----
        dummy = QFrame(objectName="DummyBar")
        dummy_lay = QHBoxLayout(dummy)
        dummy_lay.setContentsMargins(14, 10, 14, 10)
        self.dummy_button = QPushButton(DUMMY_BUTTON_FILL, objectName="DummyButton")
        self.dummy_button.setCursor(Qt.PointingHandCursor)
        self.dummy_button.clicked.connect(self.toggle_dummy_data)
        dummy_lay.addWidget(self.dummy_button)
        self.dummy_status = wrapped_label(DUMMY_STATUS_IDLE, "DummyStatus")
        dummy_lay.addWidget(self.dummy_status, 1)
        self.form_layout.addWidget(dummy)

        # ---- ① 発行日 ----
        form = self._card("① 発行日", "この請求書を発行する日付です。通常は今日の日付でかまいません。")
        self.issue_date_edit = self._date_edit()
        self.issue_reiwa_hint = QLabel(objectName="Hint")
        self.issue_date_edit.dateChanged.connect(self._update_reiwa_hints)
        form.addRow("発行日", self._hbox(self.issue_date_edit, self.issue_reiwa_hint, stretch=True))
        self._line(form, "請求書番号", "invoice_number", width=220,
                   hint="任意。領収証にも同じ番号が印字されます")

        # ---- ② 宛先 ----
        form = self._card(
            "② 宛先（請求する相手）",
            "請求書を送る相手の情報です。「御中」は自動で印字されるので入力不要です。\n"
            "一度入力した取引先は自動的に記憶され、次回から名前を選ぶだけで住所などが自動入力されます。",
        )
        self.dest_combo = QComboBox()
        self.dest_combo.setEditable(True)
        self.dest_combo.setInsertPolicy(QComboBox.NoInsert)
        self.dest_combo.lineEdit().setPlaceholderText("名前の一部を入力すると、過去の取引先の候補が出ます")
        completer = QCompleter(self.dest_combo.model(), self.dest_combo)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.activated.connect(self._on_dest_name_selected)
        self.dest_combo.setCompleter(completer)
        self.dest_combo.textActivated.connect(self._on_dest_name_selected)
        self.dest_combo.lineEdit().editingFinished.connect(
            lambda: self._on_dest_name_selected(self.dest_combo.currentText())
        )
        self.f["dest_name"] = self.dest_combo.lineEdit()
        manage_btn = QPushButton("取引先の履歴を管理")
        manage_btn.clicked.connect(self.manage_destinations)
        form.addRow("会社名・団体名", self._hbox(self.dest_combo, manage_btn, expand_first=True))
        self._line(form, "郵便番号", "dest_zip", width=160, placeholder="例：100-0001")
        self._line(form, "住所", "dest_addr")
        form.addRow("電話番号", self._tel_fax_row("dest_tel", "dest_fax"))

        # ---- ③ 請求元 ----
        form = self._card(
            "③ 請求元（あなたの情報）",
            "あなた（請求する側）の情報です。請求書の右上にまとめて印字されます。会社印の画像もここで設定します。",
        )
        self._line(form, "事務所の名称", "issuer_name")
        self._line(form, "代表者名", "issuer_representative", width=320)
        self._line(form, "郵便番号", "issuer_zip", width=160)
        self._line(form, "住所", "issuer_address")
        form.addRow("電話番号", self._tel_fax_row("issuer_tel", "issuer_fax"))
        self.show_issuer_check = QCheckBox("この情報を請求書に印字する（チェックを外すと右上に印字されません）")
        self.show_issuer_check.setToolTip(
            "すでに印刷済みの用紙（レターヘッド等）を使う場合など、\nこの情報を印字したくないときはチェックを外してください。"
        )
        form.addRow("", self.show_issuer_check)
        self.seal_thumb = QLabel("未設定", objectName="SealThumb", alignment=Qt.AlignCenter)
        self.seal_thumb.setFixedSize(64, 64)
        self.seal_name = QLabel(objectName="Hint")
        choose = QPushButton("印鑑画像を選ぶ")
        choose.clicked.connect(self.choose_seal)
        clear = QPushButton("設定を消す")
        clear.clicked.connect(self.clear_seal)
        seal_row = self._hbox(self.seal_thumb, self.seal_name, choose, clear, stretch=True)
        seal_row.setToolTip("PNG画像がおすすめです（背景が透明な印影画像がきれいに仕上がります）。\n一度選ぶと次回からも自動的に使われます。")
        form.addRow("会社印（ハンコ）", seal_row)

        # ---- ④ 品目 ----
        lay = self._card("④ 請求する内容（品目）",
                         "請求する内容を1行ずつ入力してください。金額は自動計算されます。数字は全角でも大丈夫です。",
                         form=False)
        self.show_note_check = QCheckBox("請求書の表に「摘要」欄を表示する（チェックを外すと表から摘要欄が消え、他の列が広くなります）")
        lay.addWidget(self.show_note_check)
        self.items_table = InputTable(
            columns=[
                ("日付", 96, Qt.AlignLeft), ("品名", None, Qt.AlignLeft), ("数量", 64, Qt.AlignRight),
                ("単価", 104, Qt.AlignRight), ("金額（自動）", 116, Qt.AlignRight),
                ("消費税", 92, Qt.AlignRight), ("摘要", 150, Qt.AlignLeft),
            ],
            defaults=["", "", "1", "", "", "", ""],
            blank_check_cols=(0, 1, 3, 6),
            computed_col=4,
            compute=lambda v: format_yen(self._row_amount(v)),
        )
        self.items_table.changed.connect(self._recalc_total)
        lay.addWidget(self.items_table)
        add_item = QPushButton("＋ 行を追加")
        add_item.clicked.connect(lambda: self.items_table.add_row())
        self.total_value = QLabel("￥0", objectName="TotalValue")
        lay.addWidget(self._hbox(add_item, QLabel("税込合計金額", objectName="TotalLabel"), self.total_value,
                                 stretch_at=1))

        # ---- ⑤ 備考欄 ----
        lay = self._card("⑤ 備考欄（任意）", "伝えたいことがあれば自由に入力してください（空欄でも構いません）。", form=False)
        self.remarks_edit = QPlainTextEdit()
        self.remarks_edit.setFixedHeight(84)
        lay.addWidget(self.remarks_edit)

        # ---- ⑥ 振込先 ----
        lay = self._card("⑥ 振込先", "一度入力すれば、次回からも自動的に残ります。", form=False)
        form = QFormLayout()
        self._setup_form(form)
        self._line(form, "名義人", "bank_holder1", placeholder="例：〇〇 代表者名")
        self._line(form, "住所・電話など", "bank_holder2", placeholder="任意")
        lay.addLayout(form)
        self.banks_table = InputTable(
            columns=[
                ("金融機関名", None, Qt.AlignLeft), ("支店名", 120, Qt.AlignLeft), ("店番", 76, Qt.AlignLeft),
                ("口座種類", 96, Qt.AlignLeft), ("口座番号", 140, Qt.AlignLeft),
            ],
            defaults=["", "", "", "普通", ""],
            blank_check_cols=(0, 1, 4),
        )
        lay.addWidget(self.banks_table)
        add_bank = QPushButton("＋ 振込先を追加")
        add_bank.clicked.connect(lambda: self.banks_table.add_row())
        lay.addWidget(self._hbox(add_bank, stretch=True))

        # ---- ⑦ 領収証 ----
        form = self._card(
            "⑦ 領収証（任意）",
            "領収証PDFも作りたいときに入力してください。入力しなくても領収証は作れます\n"
            "（その場合、領収日は①の発行日、但し書きは「お品代」になります）。",
        )
        self.receipt_same_check = QCheckBox("領収日は「① 発行日」と同じにする")
        self.receipt_same_check.setChecked(True)
        form.addRow("", self.receipt_same_check)
        self.receipt_date_edit = self._date_edit()
        self.receipt_reiwa_hint = QLabel(objectName="Hint")
        self.receipt_date_edit.dateChanged.connect(self._update_reiwa_hints)
        self.receipt_same_check.toggled.connect(self._update_reiwa_hints)
        form.addRow("領収日", self._hbox(self.receipt_date_edit, self.receipt_reiwa_hint, stretch=True))
        self.receipt_note = QLineEdit("お品代")
        form.addRow("但し書き（〜として）", self.receipt_note)

        self.form_layout.addStretch(1)
        return scroll

    def _build_preview(self):
        panel = QFrame(objectName="PreviewPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("プレビュー", objectName="PreviewTitle"))
        # 今どちらの書式で見ているかを、プレビューの見出しの横にも出しておく
        self.preview_format_chip = QLabel(objectName="FormatChip")
        top.addWidget(self.preview_format_chip)
        top.addSpacing(10)
        self.preview_group = QButtonGroup(self)
        for i, label in enumerate(("請求書", "領収証")):
            btn = QPushButton(label, objectName="Segment", checkable=True)
            btn.setCursor(Qt.PointingHandCursor)
            self.preview_group.addButton(btn, i)
            top.addWidget(btn)
        self.preview_group.button(0).setChecked(True)
        self.preview_group.idClicked.connect(lambda _: self._update_preview())
        top.addStretch(1)
        refresh = QPushButton("今すぐ更新")
        refresh.clicked.connect(self._update_preview)
        top.addWidget(refresh)
        lay.addLayout(top)

        self.preview_status = QLabel("入力すると自動でプレビューされます", objectName="Hint")
        lay.addWidget(self.preview_status)

        self.preview_scroll = QScrollArea(objectName="PreviewScroll")
        self.preview_scroll.setWidgetResizable(True)
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder_lay = QVBoxLayout(holder)
        holder_lay.setContentsMargins(8, 8, 8, 16)
        self.preview_page = QLabel(objectName="PreviewPage", alignment=Qt.AlignCenter)
        shadow = QGraphicsDropShadowEffect(blurRadius=24, xOffset=0, yOffset=4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.preview_page.setGraphicsEffect(shadow)
        if PDF_PREVIEW_AVAILABLE:
            self.preview_page.setText("ここに請求書／領収証のプレビューが表示されます")
        else:
            self.preview_page.setTextFormat(Qt.RichText)
            self.preview_page.setWordWrap(True)
            set_wrapped_text(
                self.preview_page,
                "プレビュー機能を使うには、追加のライブラリ（PyMuPDF）が必要です。\n"
                "01_setup をもう一度実行すると入ります。\n"
                "※ プレビューが使えなくても、PDFの作成自体は通常通り行えます。",
            )
        holder_lay.addWidget(self.preview_page, 0, Qt.AlignHCenter | Qt.AlignTop)
        holder_lay.addStretch(1)
        self.preview_scroll.setWidget(holder)
        lay.addWidget(self.preview_scroll, 1)
        return panel

    def _build_action_bar(self):
        bar = QFrame(objectName="ActionBar")
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(20, 12, 20, 8)
        outer.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(14)
        for text, name, slot, caption in (
            ("📄 請求書PDFを作成", "PrimaryInvoice", self.on_create_pdf,
             "保存場所を選ぶ画面が開きます。分かりやすい場所（デスクトップなど）を選んでください。"),
            ("🧾 領収証PDFを作成", "PrimaryReceipt", self.on_create_receipt,
             "今入力している内容（宛先・金額・発行元など）をもとに、領収証PDFを作成します。"),
            ("📑 請求書・領収証を一括作成", "PrimaryBoth", self.on_create_both,
             "保存するフォルダを1回選ぶだけで、両方のPDFをまとめて作成します。"),
        ):
            col = QVBoxLayout()
            col.setSpacing(4)
            btn = QPushButton(text, objectName=name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            col.addWidget(btn)
            col.addWidget(wrapped_label(caption, "ActionCaption"))
            row.addLayout(col, 1)
        outer.addLayout(row)
        outer.addWidget(QLabel(
            f"{APP_VERSION}　|　開発：{APP_CREDIT}　|　サポート：{APP_SUPPORT_EMAIL}",
            objectName="Footer", alignment=Qt.AlignCenter,
        ))
        return bar

    # ---- 組み立て用の小さな部品 ----
    def _card(self, title, help_text="", form=True):
        """白いカード（区切り）を1つ作り、中身を入れるレイアウトを返す。"""
        card = QFrame(objectName="Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(10)
        lay.addWidget(QLabel(title, objectName="CardTitle"))
        if help_text:
            lay.addWidget(wrapped_label(help_text))
        self.form_layout.addWidget(card)
        if not form:
            return lay
        form_lay = QFormLayout()
        self._setup_form(form_lay)
        lay.addLayout(form_lay)
        return form_lay

    @staticmethod
    def _setup_form(form):
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)

    def _line(self, form, label, key, width=None, placeholder="", hint=""):
        edit = QLineEdit()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        self.f[key] = edit
        if width:
            edit.setFixedWidth(width)
        if hint:
            form.addRow(label, self._hbox(edit, QLabel(hint, objectName="Hint"), stretch=True))
        elif width:
            form.addRow(label, self._hbox(edit, stretch=True))
        else:
            form.addRow(label, edit)
        return edit

    def _tel_fax_row(self, tel_key, fax_key):
        tel = QLineEdit()
        tel.setFixedWidth(200)
        fax = QLineEdit()
        fax.setFixedWidth(200)
        fax.setPlaceholderText("なければ空欄")
        self.f[tel_key] = tel
        self.f[fax_key] = fax
        return self._hbox(tel, QLabel("FAX番号"), fax, stretch=True)

    @staticmethod
    def _hbox(*widgets, stretch=False, expand_first=False, stretch_at=None):
        """部品を横に並べる。stretch=True なら右側に余白を入れて左に寄せ、
        stretch_at=i なら i 番目の部品の手前に余白を入れる（0 なら全部を右に寄せる）。"""
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        for i, w in enumerate(widgets):
            if stretch_at == i:
                lay.addStretch(1)
            lay.addWidget(w, 1 if (expand_first and i == 0) else 0)
        if stretch:
            lay.addStretch(1)
        return box

    @staticmethod
    def _date_edit():
        edit = QDateEdit(QDate.currentDate())
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy年M月d日")
        edit.setFixedWidth(180)
        return edit

    # ============================================================ 変更の検知・プレビュー
    def _connect_change_signals(self):
        """入力が変わったら（少し待ってから）プレビューを更新する。"""
        for edit in self.findChildren(QLineEdit):
            edit.textChanged.connect(self._schedule_preview)
        self.remarks_edit.textChanged.connect(self._schedule_preview)
        for check in (self.show_issuer_check, self.show_note_check, self.receipt_same_check):
            check.toggled.connect(self._schedule_preview)
        for edit in (self.issue_date_edit, self.receipt_date_edit):
            edit.dateChanged.connect(self._schedule_preview)
        self.items_table.changed.connect(self._schedule_preview)
        self.banks_table.changed.connect(self._schedule_preview)

    def _schedule_preview(self, *_):
        if PDF_PREVIEW_AVAILABLE:
            self._preview_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_preview()

    def _update_preview(self):
        if not PDF_PREVIEW_AVAILABLE:
            return
        try:
            if self.preview_group.checkedId() == 1:
                data = self._collect_receipt_data(self._receipt_date())
                build_fn = self._receipt_builder()
            else:
                data = self._collect_invoice_data(self._issue_date())
                build_fn = self._invoice_builder()
            buf = BytesIO()
            build_fn(buf, data)

            doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
            page = doc[0]
            target_w = max(200, self.preview_scroll.viewport().width() - 40)
            zoom = max(0.3, min(target_w / page.rect.width, 3.0))
            # 高解像度の画面でもぼやけないよう、画面の拡大率ぶん細かく描く
            ratio = self.devicePixelRatioF()
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom * ratio, zoom * ratio))
            png = pix.tobytes("png")
            doc.close()

            pixmap = QPixmap()
            pixmap.loadFromData(png)
            pixmap.setDevicePixelRatio(ratio)
            self.preview_page.setPixmap(pixmap)
            self.preview_status.setText("最終更新：" + datetime.datetime.now().strftime("%H:%M:%S"))
        except Exception:
            self.preview_status.setText("入力内容を確認してください（プレビュー未更新）")

    def _update_reiwa_hints(self, *_):
        self.issue_reiwa_hint.setText(f"PDFには「{to_reiwa(self._issue_date())}」と印字されます")
        same = self.receipt_same_check.isChecked()
        self.receipt_date_edit.setEnabled(not same)
        self.receipt_reiwa_hint.setText(f"「{to_reiwa(self._receipt_date())}」と印字されます")

    # ============================================================ 書式・配置
    def _on_doc_format_changed(self, *_):
        self.cfg["doc_format"] = self.format_combo.currentData()
        save_config(self.cfg)
        self._update_format_chip()
        self._schedule_preview()

    def _update_format_chip(self):
        self.preview_format_chip.setText(f"書式：{self.format_combo.currentText()}")

    def _invoice_builder(self):
        from pdf_builder import build_invoice_pdf, build_invoice_pdf_classic
        return build_invoice_pdf_classic if self.format_combo.currentData() == "classic" else build_invoice_pdf

    def _receipt_builder(self):
        from pdf_builder import build_receipt_pdf, build_receipt_pdf_classic
        return build_receipt_pdf_classic if self.format_combo.currentData() == "classic" else build_receipt_pdf

    def _reset_pane_layout(self):
        """左（入力欄）と右（プレビュー）の幅を、既定の 3：2 に戻す。"""
        width = self.splitter.width()
        self.splitter.setSizes([int(width * 0.6), width - int(width * 0.6)])
        self._schedule_preview()

    # ============================================================ 品目の計算
    @staticmethod
    def _row_amount(values):
        qty = parse_number(values[2])
        price = parse_number(values[3])
        if qty is None or price is None:
            return 0.0
        return qty * price

    @staticmethod
    def _row_tax(values):
        tax = parse_number(values[5])
        return tax or 0.0

    def _item_rows(self):
        """入力のある品目の行（値のリスト）。"""
        t = self.items_table
        return [t.row_values(r) for r in range(t.rowCount()) if not t.is_blank(r)]

    def _total(self):
        return sum(self._row_amount(v) + self._row_tax(v) for v in self._item_rows())

    def _recalc_total(self):
        self.total_value.setText(format_yen(self._total()))

    # ============================================================ 設定の読み込み・保存
    def _load_defaults_into_form(self):
        cfg = self.cfg
        for key in ("issuer_zip", "issuer_address", "issuer_name", "issuer_representative",
                    "issuer_tel", "issuer_fax"):
            self.f[key].setText(cfg.get(key, ""))
        self.f["bank_holder1"].setText(cfg.get("bank_holder_line1", ""))
        self.f["bank_holder2"].setText(cfg.get("bank_holder_line2", ""))
        self.show_issuer_check.setChecked(bool(cfg.get("show_issuer_block", True)))
        self.show_note_check.setChecked(bool(cfg.get("show_note_column", True)))
        self.remarks_edit.setPlainText(cfg.get("remarks_default", ""))
        self._refresh_destination_list()
        self.dest_combo.setEditText("")

        for _ in range(3):
            self.items_table.add_row()
        banks = [b for b in (cfg.get("banks") or []) if any(b.values())]
        for b in banks or [None]:
            if b is None:
                self.banks_table.add_row()
            else:
                self.banks_table.add_row([b.get("name", ""), b.get("branch", ""), b.get("code", ""),
                                          b.get("type", "普通"), b.get("number", "")])
        self._refresh_seal_display()
        self._update_reiwa_hints()
        self._update_format_chip()
        self._recalc_total()

    def _save_current_settings(self):
        if self._dummy_active:
            return  # ダミーデータ使用中は、本番の設定・取引先履歴を上書きしない
        for key in ("issuer_zip", "issuer_address", "issuer_name", "issuer_representative",
                    "issuer_tel", "issuer_fax"):
            self.cfg[key] = self.f[key].text().strip()
        self.cfg["show_issuer_block"] = self.show_issuer_check.isChecked()
        self.cfg["show_note_column"] = self.show_note_check.isChecked()
        self.cfg["bank_holder_line1"] = self.f["bank_holder1"].text().strip()
        self.cfg["bank_holder_line2"] = self.f["bank_holder2"].text().strip()
        self.cfg["remarks_default"] = self.remarks_edit.toPlainText().strip()
        self.cfg["banks"] = self._banks()
        self._remember_current_destination()
        save_config(self.cfg)

    # ============================================================ 取引先（宛先）の履歴
    def _remember_current_destination(self):
        """今入力されている宛先を、次回以降も選べるように履歴へ保存する。
        同じ名前がすでにあれば、最新の内容で上書きしたうえで一番上に移動する。"""
        name = self.f["dest_name"].text().strip()
        if not name:
            return
        entry = {
            "name": name,
            "zip": self.f["dest_zip"].text().strip(),
            "addr": self.f["dest_addr"].text().strip(),
            "tel": self.f["dest_tel"].text().strip(),
            "fax": self.f["dest_fax"].text().strip(),
        }
        destinations = [d for d in self.cfg.get("destinations", []) if d.get("name") != name]
        destinations.insert(0, entry)
        self.cfg["destinations"] = destinations[:MAX_DESTINATION_HISTORY]
        self._refresh_destination_list()

    def _refresh_destination_list(self):
        current = self.dest_combo.currentText()
        self.dest_combo.blockSignals(True)
        self.dest_combo.clear()
        self.dest_combo.addItems([d.get("name", "") for d in self.cfg.get("destinations", [])])
        self.dest_combo.setEditText(current)
        self.dest_combo.blockSignals(False)

    def _on_dest_name_selected(self, name):
        name = (name or "").strip()
        for d in self.cfg.get("destinations", []):
            if d.get("name") == name:
                self.f["dest_zip"].setText(d.get("zip", ""))
                self.f["dest_addr"].setText(d.get("addr", ""))
                self.f["dest_tel"].setText(d.get("tel", ""))
                self.f["dest_fax"].setText(d.get("fax", ""))
                break
        self._schedule_preview()

    def manage_destinations(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("取引先の履歴を管理")
        dlg.resize(460, 480)
        lay = QVBoxLayout(dlg)
        lay.addWidget(wrapped_label("これまでに入力した取引先（宛先）の一覧です。\n"
                                    "使わないもの・入力を間違えたものは、選んで削除できます。", "Hint"))
        listbox = QListWidget()
        lay.addWidget(listbox, 1)

        def _reload():
            listbox.clear()
            listbox.addItems([d.get("name", "") for d in self.cfg.get("destinations", [])])

        def _delete_selected():
            item = listbox.currentItem()
            if item is None:
                show_info(dlg, "お知らせ", "削除する取引先を、リストから選んでください。")
                return
            name = item.text()
            if not ask_yes_no(dlg, "確認", f"「{name}」を履歴から削除しますか？\n（現在入力中の内容は消えません）"):
                return
            self.cfg["destinations"] = [d for d in self.cfg.get("destinations", []) if d.get("name") != name]
            save_config(self.cfg)
            self._refresh_destination_list()
            _reload()

        _reload()
        delete_btn = QPushButton("選んだ取引先を削除")
        delete_btn.clicked.connect(_delete_selected)
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(self._hbox(delete_btn, close_btn, stretch_at=1))
        dlg.exec()

    # ============================================================ 印鑑画像
    def choose_seal(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "会社印（ハンコ）の画像ファイルを選んでください", "",
            "画像ファイル (*.png *.jpg *.jpeg *.gif *.bmp);;すべてのファイル (*)",
        )
        if path:
            self.cfg["seal_image_path"] = path
            save_config(self.cfg)
            self._refresh_seal_display()
            show_info(self, "設定完了", "印鑑画像を設定しました。\n次回からも自動的に使われます。")
            self._schedule_preview()

    def clear_seal(self):
        self.cfg["seal_image_path"] = ""
        save_config(self.cfg)
        self._refresh_seal_display()
        self._schedule_preview()

    def _current_seal_path(self):
        """PDFに使う印影画像。会社印が未設定で、ダミーデータ使用中ならダミーの印影を使う。"""
        seal = self.cfg.get("seal_image_path", "")
        if not seal and self._dummy_seal and os.path.exists(DUMMY_SEAL_PATH):
            return DUMMY_SEAL_PATH
        return seal

    def _refresh_seal_display(self):
        path = self._current_seal_path()
        pixmap = QPixmap(path) if path and os.path.exists(path) else QPixmap()
        if pixmap.isNull():
            self.seal_thumb.setPixmap(QPixmap())
            if path:
                # 設定はされているが、ファイルが無い／画像として読めない
                self.seal_thumb.setText("！")
                self.seal_name.setText(f"（画像を読み込めませんでした：{os.path.basename(path)}）")
            else:
                self.seal_thumb.setText("未設定")
                self.seal_name.setText("（未設定）")
            return
        self.seal_thumb.setPixmap(pixmap.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if path == DUMMY_SEAL_PATH:
            self.seal_name.setText("（ダミーの会社印「見本之印」を使用中）")
        else:
            self.seal_name.setText(os.path.basename(path))

    # ============================================================ ヘルプ・アップデート
    def show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("使い方ヘルプ")
        dlg.resize(680, 680)
        lay = QVBoxLayout(dlg)
        text = QTextBrowser()
        # 行間を広げ、字下げ（行頭の空白）はそのまま残して表示する
        text.setHtml(f'<div style="line-height:150%; white-space:pre-wrap;">{html.escape(HELP_TEXT)}</div>')
        lay.addWidget(text, 1)
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(self._hbox(close_btn, stretch_at=0))
        dlg.exec()

    def check_for_updates(self):
        import updater

        if not updater.is_configured(UPDATE_MANIFEST_URL):
            show_info(self, "お知らせ", "アップデート機能はまだ準備中です。\n開発者にご確認ください。")
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            info = updater.check_for_update(UPDATE_MANIFEST_URL)
        except updater.UpdateError as e:
            QApplication.restoreOverrideCursor()
            show_warning(
                self, "確認できませんでした",
                "アップデートの確認ができませんでした。\n"
                "インターネットに接続されているかご確認のうえ、\n"
                "もう一度お試しください。\n\n"
                f"（技術情報）{e}",
            )
            return
        QApplication.restoreOverrideCursor()

        remote_v = info.get("version", "0")
        notes = info.get("notes", "")
        if updater.parse_version(remote_v) <= updater.parse_version(APP_VERSION_NUM):
            show_info(self, "お知らせ", f"お使いの{APP_VERSION}は最新です。")
            return

        if getattr(sys, "frozen", False):
            # exe/deb版は、ZIPを上書きする今の更新方式が使えない
            # （フォルダの中身をまるごと入れ替える前提の仕組みのため）。
            # 新しいインストーラーをダウンロードしてもらうよう案内する。
            msg = f"新しいバージョン（{remote_v}）が公開されています。\n"
            if notes:
                msg += f"\n【更新内容】\n{notes}\n"
            msg += ("\nこの版（exe/deb）は自動更新に対応していないため、"
                    "配布ページから新しいインストーラーをダウンロードして、入れ直してください。")
            show_info(self, "新しいバージョンがあります", msg)
            return

        msg = f"新しいバージョン（{remote_v}）が見つかりました。\n今すぐ更新しますか？"
        if notes:
            msg += f"\n\n【更新内容】\n{notes}"
        if not ask_yes_no(self, "アップデートがあります", msg):
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            updater.download_and_apply_update(info["zip_url"], APP_DIR)
        except updater.UpdateError as e:
            QApplication.restoreOverrideCursor()
            show_error(
                self, "更新に失敗しました",
                "アップデートの適用中に問題が発生しました。\n"
                "お手数ですが、開発者にご連絡ください。\n\n"
                f"（技術情報）{e}",
            )
            return
        QApplication.restoreOverrideCursor()

        show_info(
            self, "更新が完了しました",
            "アップデートが完了しました。\n"
            "変更を反映するため、いったんこのツールを閉じます。\n"
            "閉じたあと、もう一度デスクトップのアイコンから開き直してください。",
        )
        QApplication.quit()

    # ============================================================ ダミーデータ（出力テスト用）
    def toggle_dummy_data(self):
        if self._dummy_active:
            self.clear_dummy_data()
        else:
            self.fill_dummy_data()

    def fill_dummy_data(self):
        """空いている欄だけにダミーデータを入れる（入力済みの欄はそのまま）。
        会社印が未設定なら、1:1の「見本之印」の画像を作って使う。
        入れた場所には目印を付け、clear_dummy_data で元に戻せるようにする。"""
        for key, value in DUMMY_FIELDS.items():
            edit = self.f[key]
            if not edit.text().strip():
                edit.setText(value)
                edit.setProperty(DUMMY_PROP, value)
        if not self.remarks_edit.toPlainText().strip():
            self.remarks_edit.setPlainText(DUMMY_REMARKS)
            self._dummy_remarks = True

        # 品目は「金額（自動）」の列をとばして並べる
        self.items_table.fill_dummy([(d, n, q, p, None, t, note) for d, n, q, p, t, note in DUMMY_ITEMS])
        self.banks_table.fill_dummy(DUMMY_BANKS)

        if not self.cfg.get("seal_image_path"):
            try:
                from pdf_builder import build_dummy_seal_png
                build_dummy_seal_png(DUMMY_SEAL_PATH)
                self._dummy_seal = True
            except Exception:
                pass  # 印影が作れなくても、ほかのダミーデータでの出力テストはできる

        self._dummy_active = True
        self._refresh_seal_display()
        self._set_dummy_status(True)
        self._recalc_total()
        self._schedule_preview()

    def clear_dummy_data(self):
        """fill_dummy_data で入れた欄を空欄に戻す。ダミーを入れたあとに
        書き換えた欄は、本物の内容かもしれないので消さずに残す。"""
        for edit in self.f.values():
            value = edit.property(DUMMY_PROP)
            if value is not None:
                if edit.text() == value:
                    edit.clear()
                edit.setProperty(DUMMY_PROP, None)
        if self._dummy_remarks and self.remarks_edit.toPlainText().strip() == DUMMY_REMARKS:
            self.remarks_edit.clear()
        self._dummy_remarks = False
        self.items_table.clear_dummy()
        self.banks_table.clear_dummy()

        self._dummy_seal = False
        self._dummy_active = False
        self._refresh_seal_display()
        self._set_dummy_status(False)
        self._recalc_total()
        self._schedule_preview()

    def _set_dummy_status(self, active):
        self.dummy_button.setText(DUMMY_BUTTON_CLEAR if active else DUMMY_BUTTON_FILL)
        set_wrapped_text(self.dummy_status, DUMMY_STATUS_ACTIVE if active else DUMMY_STATUS_IDLE)
        # 文字色はスタイルシートの [active="true"] で切り替える
        self.dummy_status.setProperty("active", active)
        self.dummy_status.style().unpolish(self.dummy_status)
        self.dummy_status.style().polish(self.dummy_status)

    # ============================================================ 入力チェック
    def _validate(self):
        errors = []
        if not self.f["dest_name"].text().strip():
            errors.append("『② 宛先』の会社名・団体名が入力されていません。")

        t = self.items_table
        any_item = False
        for r in range(t.rowCount()):
            if t.is_blank(r):
                continue
            any_item = True
            values = t.row_values(r)
            for col, label in ((3, "単価"), (2, "数量"), (5, "消費税")):
                if parse_number(values[col]) is None:
                    errors.append(f"『④ 品目』{r + 1}行目の{label}は数字で入力してください。")
        if not any_item:
            errors.append("『④ 品目』が1件も入力されていません。少なくとも1行は入力してください。")

        errors.extend(self._seal_errors())
        return errors

    def _validate_receipt(self):
        errors = []
        if not self.f["dest_name"].text().strip():
            errors.append("『② 宛先』の会社名・団体名が入力されていません。")
        if self._total() <= 0:
            errors.append("金額が入力されていません。『④ 品目』欄に内容を入力してください。")
        errors.extend(self._seal_errors())
        return errors

    def _seal_errors(self):
        seal = self.cfg.get("seal_image_path")
        if seal and not os.path.exists(seal):
            return ["設定されている印鑑画像が見つかりません。もう一度『印鑑画像を選ぶ』からやり直してください。"]
        return []

    # ============================================================ データ収集（PDF作成・プレビュー共通）
    def _issue_date(self):
        return self.issue_date_edit.date().toPython()

    def _receipt_date(self):
        if self.receipt_same_check.isChecked():
            return self._issue_date()
        return self.receipt_date_edit.date().toPython()

    def _items(self):
        items = []
        for v in self._item_rows():
            items.append({
                "date": v[0].strip(),
                "name": v[1].strip(),
                "qty": normalize_number(v[2]),
                "price": normalize_number(v[3]),
                "amount": self._row_amount(v),
                "tax": normalize_number(v[5]),
                "note": v[6].strip(),
            })
        return items

    def _banks(self):
        t = self.banks_table
        banks = []
        for r in range(t.rowCount()):
            if t.is_blank(r):
                continue
            name, branch, code, acc_type, number = (s.strip() for s in t.row_values(r))
            banks.append({"name": name, "branch": branch, "code": code,
                          "type": acc_type or "普通", "number": number})
        return banks

    def _common_data(self, doc_date):
        data = {"issue_date": doc_date}
        for key in ("invoice_number", "dest_name", "dest_zip", "dest_addr", "dest_tel", "dest_fax",
                    "issuer_zip", "issuer_address", "issuer_name", "issuer_representative",
                    "issuer_tel", "issuer_fax"):
            data[key] = self.f[key].text().strip()
        data["show_issuer_block"] = self.show_issuer_check.isChecked()
        data["show_note_column"] = self.show_note_check.isChecked()
        data["seal_path"] = self._current_seal_path()
        data["items"] = self._items()
        data["total"] = self._total()
        return data

    def _collect_invoice_data(self, issue_date):
        data = self._common_data(issue_date)
        data.update({
            "remarks": self.remarks_edit.toPlainText().strip(),
            "bank_holder1": self.f["bank_holder1"].text().strip(),
            "bank_holder2": self.f["bank_holder2"].text().strip(),
            "banks": self._banks(),
        })
        return data

    def _collect_receipt_data(self, receipt_date):
        data = self._common_data(receipt_date)
        data.update({
            "tax_total": sum(self._row_tax(v) for v in self._item_rows()),
            "remarks": self.receipt_note.text().strip() or "お品代",
        })
        return data

    # ============================================================ PDF作成
    def _build_pdf(self, label, build_fn, path, data):
        """PDFを1つ作る。失敗したらメッセージを出して False を返す。"""
        try:
            build_fn(path, data)
            return True
        except Exception:
            err = traceback.format_exc()
            show_error(
                self, "PDFの作成に失敗しました",
                f"申し訳ありません、{label}PDFの作成中に問題が発生しました。\n"
                "入力内容をもう一度ご確認のうえ、お試しください。\n\n"
                "（技術情報）\n" + err[-800:],
            )
            return False

    def _create_single(self, label, errors, date, collect, builder):
        if errors:
            show_warning(self, "入力内容を確認してください", "\n\n".join(errors))
            return
        self._save_current_settings()
        data = collect(date)
        default_name = f"{label}_{date.strftime('%Y%m%d')}_{data['dest_name'] or '宛先未設定'}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, f"{label}PDFの保存先を選んでください",
            os.path.join(self._default_save_dir(), safe_filename(default_name)),
            "PDFファイル (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if not self._build_pdf(label, builder, path, data):
            return
        self.cfg["last_save_dir"] = os.path.dirname(path)
        save_config(self.cfg)
        if ask_yes_no(self, "完成しました", f"{label}PDFを作成しました。\n\n{path}\n\nこのファイルを開きますか？"):
            self._open_path(path)

    def on_create_pdf(self):
        self._create_single("請求書", self._validate(), self._issue_date(),
                            self._collect_invoice_data, self._invoice_builder())

    def on_create_receipt(self):
        self._create_single("領収証", self._validate_receipt(), self._receipt_date(),
                            self._collect_receipt_data, self._receipt_builder())

    def on_create_both(self):
        # 請求書・領収証の両方の入力チェックをまとめて表示する（同じ指摘は1回だけ）
        errors = list(dict.fromkeys(self._validate() + self._validate_receipt()))
        if errors:
            show_warning(self, "入力内容を確認してください", "\n\n".join(errors))
            return
        self._save_current_settings()

        issue_date, receipt_date = self._issue_date(), self._receipt_date()
        invoice_data = self._collect_invoice_data(issue_date)
        receipt_data = self._collect_receipt_data(receipt_date)
        dest = invoice_data["dest_name"] or "宛先未設定"

        folder = QFileDialog.getExistingDirectory(
            self, "請求書・領収証PDFを保存するフォルダを選んでください", self._default_save_dir(),
        )
        if not folder:
            return
        jobs = [
            ("請求書", os.path.join(folder, safe_filename(f"請求書_{issue_date.strftime('%Y%m%d')}_{dest}.pdf")),
             self._invoice_builder(), invoice_data),
            ("領収証", os.path.join(folder, safe_filename(f"領収証_{receipt_date.strftime('%Y%m%d')}_{dest}.pdf")),
             self._receipt_builder(), receipt_data),
        ]
        existing = [os.path.basename(path) for _, path, _, _ in jobs if os.path.exists(path)]
        if existing and not ask_yes_no(
            self, "上書きの確認", "同じ名前のファイルがすでにあります。上書きしますか？\n\n" + "\n".join(existing),
        ):
            return
        for label, path, build_fn, data in jobs:
            if not self._build_pdf(label, build_fn, path, data):
                return

        self.cfg["last_save_dir"] = folder
        save_config(self.cfg)
        paths = "\n".join(path for _, path, _, _ in jobs)
        if ask_yes_no(self, "完成しました",
                      f"請求書PDFと領収証PDFを作成しました。\n\n{paths}\n\n保存したフォルダを開きますか？"):
            self._open_path(folder)

    # ============================================================ 保存・オープン共通処理
    def _default_save_dir(self):
        default_dir = self.cfg.get("last_save_dir") or os.path.expanduser("~/Desktop")
        if not os.path.isdir(default_dir):
            default_dir = os.path.expanduser("~")
        return default_dir

    def _open_path(self, path):
        """ファイルやフォルダを、OS標準のアプリで開く。"""
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            show_info(self, "お知らせ", "ファイルは作成されましたが、自動で開けませんでした。\n保存先フォルダから開いてください。")


# ------------------------------------------------------------------
# 起動
# ------------------------------------------------------------------
def _load_bundled_font():
    """PDFと同じ「BIZ UDPGothic」を画面にも使う（同梱フォントを読み込むので、
    どのPCでも同じ見た目になる）。読み込めた書体名を返す。"""
    family = ""
    for name in ("BIZUDPGothic-Regular.ttf", "BIZUDPGothic-Bold.ttf"):
        font_id = QFontDatabase.addApplicationFont(os.path.join(common.resource_dir(), "assets", name))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        family = family or (families[0] if families else "")
    return family


def _install_japanese_translation(app):
    """Qtが用意している画面部品（カレンダー・右クリックメニューなど）を日本語にする。"""
    QLocale.setDefault(QLocale(QLocale.Japanese, QLocale.Japan))
    translator = QTranslator(app)
    if translator.load("qtbase_ja", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)


def run():
    common.migrate_old_config_if_needed()
    # Linux：Wayland が使える環境では Wayland を先に試し、だめなら X11 にする。
    # （WSL などは Wayland があっても X11 が選ばれてしまい、X11 用の部品
    #   libxcb-cursor0 が無いと起動できないため）
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY") \
            and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
    app = QApplication.instance() or QApplication(sys.argv)
    # Windowsがダークモードでも、明るい配色で表示する（この画面は明るい配色で作っているため。
    # 合わせないと、入力欄の周りだけ黒くなるなど、ちぐはぐな見た目になる）
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass  # Qt 6.8 より前は、この指定ができない（その場合は下の配色の指定だけで整える）
    app.setStyle("Fusion")
    _install_japanese_translation(app)

    family = _load_bundled_font()
    font = QFont(family) if family else QFont()
    font.setPointSizeF(10.5)
    app.setFont(font)

    palette = app.style().standardPalette()
    palette.setColor(QPalette.Window, QColor("#f3f5f9"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.PlaceholderText, QColor("#9aa4b2"))
    app.setPalette(palette)
    app.setStyleSheet(_style_sheet(_write_arrow_icon()))

    window = MainWindow()
    window.showMaximized()
    # ウィンドウの大きさが決まってから、左右の分割を既定の比率にする
    QTimer.singleShot(100, window._reset_pane_layout)
    return app.exec()
