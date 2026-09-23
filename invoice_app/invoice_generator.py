# -*- coding: utf-8 -*-
"""
請求書かんたん作成ツール
=========================
機械操作が苦手な方でも迷わずに請求書PDFを作成できるように、
できるだけ画面をシンプルにし、要所要所に説明文（ヘルプ）を入れています。

■ 使い方（かんたん3ステップ）
  1. 「宛先（請求する相手）」の欄を入力する
  2. 「請求する内容（品目）」の欄を入力する（自動で金額の合計が計算されます）
  3. 画面いちばん下の「📄 請求書PDFを作成する」ボタンを押す

分からなくなったら、画面右上の「使い方ヘルプ」ボタンをいつでも押してください。
"""

import json
import os
import shutil
import subprocess
import sys
import traceback
import datetime
from io import BytesIO
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog

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
# 起動フォルダ（この.pyファイル/ exe があるフォルダ）を基準にする
# ------------------------------------------------------------------
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _resource_dir():
    """同梱リソース（assetsフォルダ等）を探すためのフォルダ。

    PyInstallerでexe化した場合、sys.executableの場所（APP_DIR）と、
    同梱データが実際に展開される場所（sys._MEIPASS）は一致しないことが
    ある（特にonefile形式のとき）。そのため同梱リソースを探すときは
    APP_DIRではなくこちらを使う。
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return APP_DIR


def _get_user_data_dir():
    """母上が入力した設定（振込先・会社印の場所など）を保存する場所。

    ★重要★　わざと『アプリのコードが入っているフォルダ』とは
    完全に別の場所（Windowsの個人設定用フォルダ）に保存している。
    こうしておけば、開発者がアプリのフォルダをまるごとZIP化して
    GitHub等にアップロードしても、振込先などの個人情報が
    誤って一緒に公開されることがない。
    """
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    data_dir = os.path.join(base, "InvoiceGeneratorTool")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        data_dir = APP_DIR  # 万一作れなければ、従来通りアプリフォルダに保存
    return data_dir


_USER_DATA_DIR = _get_user_data_dir()
CONFIG_PATH = os.path.join(_USER_DATA_DIR, "invoice_config.json")
_OLD_CONFIG_PATH = os.path.join(APP_DIR, "invoice_config.json")  # 旧バージョンの保存場所


def _migrate_old_config_if_needed():
    """以前のバージョンで、アプリのフォルダに直接保存されていた設定を
    新しい保存場所（個人設定用フォルダ）に一度だけ引っ越す。"""
    try:
        if os.path.exists(_OLD_CONFIG_PATH) and not os.path.exists(CONFIG_PATH):
            shutil.copy2(_OLD_CONFIG_PATH, CONFIG_PATH)
            os.remove(_OLD_CONFIG_PATH)
    except Exception:
        pass  # 引っ越しに失敗しても、アプリの起動自体は続ける


_migrate_old_config_if_needed()

# ------------------------------------------------------------------
# 画面（Tkinter）用の日本語フォント選び
# ------------------------------------------------------------------
# 「Meiryo」はWindows専用のフォント名で、Linux/Macにはそのままでは
# 存在しない。決め打ちのままだと文字が四角（豆腐）で表示されてしまうため、
# 実際にこのPCで使えるフォントの中から日本語対応のものを選ぶ。
#
# 「BIZ UDPGothic」を最優先にしているのは、高齢の方にも読みやすいよう
# PDF側（pdf_builder.py）でも採用しているユニバーサルデザインフォントで、
# 画面と印刷物の書体を揃えるため（Windows 10/11には標準搭載）。
_JP_FONT_CANDIDATES = [
    "BIZ UDPGothic", "Meiryo", "Yu Gothic UI", "Yu Gothic", "MS PGothic",
    "Hiragino Sans", "Hiragino Kaku Gothic ProN",
    "Noto Sans CJK JP", "Noto Sans JP", "IPAGothic", "IPAPGothic",
    "TakaoPGothic", "VL PGothic", "Droid Sans Japanese",
]

# main() の中で、実際に使えるフォント名に置き換わる（既定値はWindows向け）。
UI_FONT_FAMILY = "Meiryo"


def _ensure_bundled_font_on_linux():
    """Linuxで日本語フォントが1つも無いPCのために、同梱のBIZ UDPGothicを
    ユーザー個人のフォントフォルダにだけインストールする（sudo不要・失敗しても無視）。

    ★ここも『個人フォルダーと分ける設計』と同じ考え方：
    システム全体（/usr/share/fonts等）には一切書き込まず、
    ~/.local/share/fonts というユーザー専用の場所だけを使う。
    こうしておけば、他のユーザーやシステム設定に影響を与えない。
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        resource_dir = _resource_dir()
        user_font_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "fonts")
        installed_any = False
        for fname, dest_name in [
            ("BIZUDPGothic-Regular.ttf", "invoice-generator-tool-bizudpgothic-regular.ttf"),
            ("BIZUDPGothic-Bold.ttf", "invoice-generator-tool-bizudpgothic-bold.ttf"),
        ]:
            src = os.path.join(resource_dir, "assets", fname)
            dest = os.path.join(user_font_dir, dest_name)
            if not os.path.exists(src) or os.path.exists(dest):
                continue
            os.makedirs(user_font_dir, exist_ok=True)
            shutil.copy2(src, dest)
            installed_any = True

        if installed_any:
            fc_cache = shutil.which("fc-cache")
            if fc_cache:
                subprocess.run(
                    [fc_cache, "-f", user_font_dir], timeout=15,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
    except Exception:
        pass  # 失敗しても起動自体は続ける（最悪、文字が四角になるだけ）


def _pick_ui_font_family(root):
    """このPCで実際に使える日本語フォントを候補リストから選ぶ。"""
    try:
        available = set(tkfont.families(root))
    except Exception:
        available = set()
    for name in _JP_FONT_CANDIDATES:
        if name in available:
            return name
    return "TkDefaultFont"


APP_VERSION_NUM = "1.4"
APP_VERSION = f"Version {APP_VERSION_NUM}"
APP_CREDIT = "ClaudeCord & 井上"
APP_SUPPORT_EMAIL = "satoshi29333104@gmail.com"

# GitHubの「Releases」機能から、最新版の情報を自動取得するURL。
# 詳しい手順（Releaseの出し方）は updater.py の一番上のコメントに書いてあります。
UPDATE_MANIFEST_URL = "https://api.github.com/repos/uhgm/InvoiceGen/releases/latest"

DEFAULT_CONFIG = {
    "seal_image_path": "",
    "issuer_name": "",
    "issuer_zip": "",
    "issuer_address": "",
    "issuer_representative": "",
    "issuer_tel": "",
    "issuer_fax": "",
    "show_issuer_block": True,
    "show_note_column": True,
    "bank_holder_line1": "",
    "bank_holder_line2": "",
    "banks": [
        {"name": "", "branch": "", "code": "", "type": "普通", "number": ""},
    ],
    "last_save_dir": "",
    "remarks_default": "",
    "destinations": [],  # 過去に入力した取引先（宛先）の履歴。新しい順。
}

MAX_DESTINATION_HISTORY = 50  # 取引先履歴の保存件数の上限


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(data)
            return merged
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        # 設定の保存に失敗しても、請求書作成自体は続けられるようにする
        pass


def to_reiwa(dt: datetime.date) -> str:
    """西暦の日付を『令和◯年◯月◯日』の文字列に変換する。"""
    reiwa_year = dt.year - 2018
    if dt.year < 2019:
        # 令和より前の日付は西暦のまま表示（想定外だが念のため）
        return f"{dt.year}年{dt.month}月{dt.day}日"
    if reiwa_year == 1:
        return f"令和元年{dt.month}月{dt.day}日"
    return f"令和{reiwa_year}年{dt.month}月{dt.day}日"


def format_yen(value) -> str:
    try:
        return "￥{:,}".format(int(round(value)))
    except Exception:
        return "￥0"


HELP_TEXT = """【使い方ガイド】

■ 全体の流れ
  ① 上から順番に、空いている欄を埋めていきます。
  ② 「品目」の表に、請求する内容（品名・数量・単価）を入力します。
     金額と合計金額は自動で計算されるので、電卓は不要です。
  ③ 一番下の「📄 請求書PDFを作成する」ボタンを押すと、保存する場所を
     聞かれるので、分かりやすい場所（例：デスクトップ）を選んで
     保存してください。

■ よくある質問
  Q. 何かの欄を間違えて入力してしまった
  A. その欄をクリックして、文字を消してから正しい内容を
     入力し直せば大丈夫です。何度でもやり直せます。

  Q. 品目の行が足りない
  A. 「＋行を追加」ボタンを押すと、入力欄が1行増えます。

  Q. 会社の印鑑（ハンコ）の画像はどこで設定するの？
  A. 「請求元（自分の情報）」の欄にある「印鑑画像を選ぶ」ボタンから、
     ハンコの画像ファイル（PNGなど）を選んでください。
     一度選ぶと、次回からは自動的に使われます。

  Q. 振込先の情報はどうなるの？
  A. 「振込先」の欄に入力した内容が、次にこのアプリを開いたときも
     残るようになっています（毎回入力し直す必要はありません）。

  Q. 前に請求した取引先に、また請求書を出したい
  A. 「② 宛先」の「会社名・団体名」欄に、名前の一部を入力すると
     過去に入力した取引先の候補が下に出てきます。候補をクリックすると
     住所・電話番号なども自動で入力されます。
     一度PDFを作成した取引先は、自動的にこの候補に追加されます。
     間違えて登録してしまったときは「取引先の履歴を管理」ボタンから
     削除できます。

  Q. 領収証も発行したい
  A. 画面いちばん下の「🧾 領収証PDFを作成する」ボタンを押すと、
     今入力している宛先・金額・発行元の情報をそのまま使って
     領収証PDFが作成されます。請求書とは別に、必要な分だけ
     作成できます。「⑦ 領収証」欄で、領収日（お金を受け取った日）や
     但し書きを変更できます（入力しなくても「お品代」として
     作成されます）。5万円以上の場合は、収入印紙欄が自動で
     印字されます（印紙そのものは含まれないので、あとで貼って
     消印してください）。

  Q. 保存する前に、出来上がりを見たい
  A. 画面右側に「プレビュー」欄があり、入力しながら自動でPDFの
     見た目が表示されます（少し待つと反映されます）。
     「請求書」「領収証」のどちらを見るかは、プレビュー欄の上にある
     ボタンで切り替えられます。うまく表示されないときは
     「🔄 今すぐ更新」ボタンを押してください。

  Q. PDFはどこに保存されるの？
  A. 「📄 請求書PDFを作成する」ボタンを押したときに出てくる画面で、
     好きな保存場所とファイル名を選べます。

  Q. 操作を間違えて、アプリがおかしくなった
  A. 一度アプリを閉じて（右上の×ボタン）、もう一度
     ショートカットから開き直してください。入力していた内容は
     消えてしまいますが、故障ではありませんので安心してください。

分からないことがあれば、いつでもこの画面を開いて確認してください。
"""


class ToolTip:
    """マウスを乗せると説明が出る、小さな吹き出しヘルプ。"""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text, justify="left", background="#ffffe0",
            relief="solid", borderwidth=1, font=(UI_FONT_FAMILY, 10), padx=6, pady=4,
            wraplength=360,
        )
        label.pack()

    def hide(self, _event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


class ItemRow:
    """品目テーブルの1行分の入力欄をまとめたクラス。"""

    def __init__(self, parent, on_change, on_remove):
        self.frame = ttk.Frame(parent)
        self.on_change = on_change

        self.date_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.qty_var = tk.StringVar(value="1")
        self.price_var = tk.StringVar()
        self.tax_var = tk.StringVar()
        self.note_var = tk.StringVar()
        self.amount_var = tk.StringVar(value="￥0")

        widths = [10, 26, 6, 10, 10, 14]
        e1 = ttk.Entry(self.frame, textvariable=self.date_var, width=widths[0])
        e2 = ttk.Entry(self.frame, textvariable=self.name_var, width=widths[1])
        e3 = ttk.Entry(self.frame, textvariable=self.qty_var, width=widths[2])
        e4 = ttk.Entry(self.frame, textvariable=self.price_var, width=widths[3])
        lbl_amount = ttk.Label(self.frame, textvariable=self.amount_var, width=widths[4], anchor="e")
        e6 = ttk.Entry(self.frame, textvariable=self.tax_var, width=8)
        e7 = ttk.Entry(self.frame, textvariable=self.note_var, width=widths[5])
        btn_del = ttk.Button(self.frame, text="削除", width=5,
                              command=lambda: on_remove(self))

        for i, w in enumerate([e1, e2, e3, e4, lbl_amount, e6, e7, btn_del]):
            w.grid(row=0, column=i, padx=2, pady=2, sticky="w")

        for var in (self.qty_var, self.price_var):
            var.trace_add("write", lambda *_: self._recalc())

        ToolTip(e1, "請求する日付（例：9月1日）")
        ToolTip(e2, "請求する内容の名前（例：準組合費 令和8年9〜11月）")
        ToolTip(e3, "個数（数字のみ）")
        ToolTip(e4, "1個あたりの値段（数字のみ、円マーク不要）")
        ToolTip(e6, "消費税額。分からなければ空欄のままでOKです")
        ToolTip(e7, "備考・補足があれば入力（任意）")

    def _recalc(self):
        try:
            qty = float(self.qty_var.get() or 0)
            price = float(self.price_var.get() or 0)
            amount = qty * price
        except ValueError:
            amount = 0
        self.amount_var.set(format_yen(amount))
        self.on_change()

    def get_amount(self):
        try:
            qty = float(self.qty_var.get() or 0)
            price = float(self.price_var.get() or 0)
            return qty * price
        except ValueError:
            return 0.0

    def get_tax(self):
        try:
            return float(self.tax_var.get() or 0)
        except ValueError:
            return 0.0

    def is_blank(self):
        return not any([
            self.date_var.get().strip(), self.name_var.get().strip(),
            self.price_var.get().strip(), self.note_var.get().strip(),
        ])

    def as_dict(self):
        return {
            "date": self.date_var.get().strip(),
            "name": self.name_var.get().strip(),
            "qty": self.qty_var.get().strip(),
            "price": self.price_var.get().strip(),
            "amount": self.get_amount(),
            "tax": self.tax_var.get().strip(),
            "note": self.note_var.get().strip(),
        }


class BankRow:
    def __init__(self, parent, on_remove):
        self.frame = ttk.Frame(parent)
        self.name_var = tk.StringVar()
        self.branch_var = tk.StringVar()
        self.code_var = tk.StringVar()
        self.type_var = tk.StringVar(value="普通")
        self.number_var = tk.StringVar()

        widths = [16, 10, 6, 6, 12]
        entries = [
            ttk.Entry(self.frame, textvariable=self.name_var, width=widths[0]),
            ttk.Entry(self.frame, textvariable=self.branch_var, width=widths[1]),
            ttk.Entry(self.frame, textvariable=self.code_var, width=widths[2]),
            ttk.Entry(self.frame, textvariable=self.type_var, width=widths[3]),
            ttk.Entry(self.frame, textvariable=self.number_var, width=widths[4]),
        ]
        for i, w in enumerate(entries):
            w.grid(row=0, column=i, padx=2, pady=2, sticky="w")
        btn = ttk.Button(self.frame, text="削除", width=5, command=lambda: on_remove(self))
        btn.grid(row=0, column=len(entries), padx=2)

        ToolTip(entries[0], "金融機関名（例：〇〇信用金庫）")
        ToolTip(entries[1], "支店名（例：千駄ヶ谷支店）")
        ToolTip(entries[2], "支店番号（分かれば入力、なくてもOK）")
        ToolTip(entries[3], "口座種類（普通 または 当座）")
        ToolTip(entries[4], "口座番号")

    def is_blank(self):
        return not any([
            self.name_var.get().strip(), self.branch_var.get().strip(),
            self.number_var.get().strip(),
        ])

    def as_dict(self):
        return {
            "name": self.name_var.get().strip(),
            "branch": self.branch_var.get().strip(),
            "code": self.code_var.get().strip(),
            "type": self.type_var.get().strip() or "普通",
            "number": self.number_var.get().strip(),
        }


class InvoiceApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self._preview_photo = None  # PhotoImageへの参照（GC対策で保持しておく）
        self._preview_after_id = None
        root.title(f"請求書かんたん作成ツール - {APP_VERSION}")
        # 右側にPDFプレビューを表示するため、画面サイズはフルHD固定にしている。
        root.geometry("1920x1080")

        self._build_layout()
        self._load_defaults_into_form()

    # ---------------------------------------------------------- UI 構築
    def _build_layout(self):
        big_font = (UI_FONT_FAMILY, 11)
        header_font = (UI_FONT_FAMILY, 14, "bold")
        self.root.option_add("*Font", big_font)

        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="請求書かんたん作成ツール", font=(UI_FONT_FAMILY, 18, "bold")).pack(side="left")
        ttk.Button(top, text="？ 使い方ヘルプ", command=self.show_help).pack(side="right")
        ttk.Button(top, text="🔄 アップデート確認", command=self.check_for_updates).pack(side="right", padx=(0, 8))

        # 画面を左右2カラムに分割：左＝入力フォーム、右＝PDFプレビュー
        main_paned = ttk.PanedWindow(self.root, orient="horizontal")
        main_paned.pack(fill="both", expand=True)

        left_pane = ttk.Frame(main_paned)
        main_paned.add(left_pane, weight=3)
        right_pane = ttk.Frame(main_paned)
        main_paned.add(right_pane, weight=2)

        self._build_preview_pane(right_pane)

        # スクロール可能な本体エリア（左カラム）
        container = ttk.Frame(left_pane)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        vscroll = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas, padding=12)
        self.body.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # 入力中は基本的にどこに入力してもプレビューを自動更新する
        self.root.bind_all("<KeyRelease>", self._schedule_preview_update)

        body = self.body

        # ---- ① 発行日 ----
        sec1 = self._section(body, "① 発行日", "この請求書を発行する日付です。通常は今日の日付でかまいません。")
        today = datetime.date.today()
        self.date_year = tk.StringVar(value=str(today.year))
        self.date_month = tk.StringVar(value=str(today.month))
        self.date_day = tk.StringVar(value=str(today.day))
        row = ttk.Frame(sec1)
        row.pack(anchor="w")
        ttk.Entry(row, textvariable=self.date_year, width=6).grid(row=0, column=0)
        ttk.Label(row, text="年（西暦）").grid(row=0, column=1, padx=(2, 10))
        ttk.Entry(row, textvariable=self.date_month, width=4).grid(row=0, column=2)
        ttk.Label(row, text="月").grid(row=0, column=3, padx=(2, 10))
        ttk.Entry(row, textvariable=self.date_day, width=4).grid(row=0, column=4)
        ttk.Label(row, text="日").grid(row=0, column=5, padx=(2, 0))
        ttk.Label(row, text="  ※ PDFには自動で「令和◯年」の形で印字されます", foreground="#666").grid(row=0, column=6, padx=10)

        self.invoice_number = self._labeled_entry(
            sec1, "請求書番号（任意・領収証にも使われます）", width=20,
        )

        # ---- ② 宛先 ----
        sec2 = self._section(
            body, "② 宛先（請求する相手）",
            "請求書を送る相手の情報です。「御中」は自動で印字されるので入力不要です。\n"
            "一度入力した取引先は自動的に記憶され、次回から名前を選ぶだけで住所などが自動入力されます。",
        )

        dest_name_row = ttk.Frame(sec2)
        dest_name_row.pack(anchor="w", pady=2, fill="x")
        ttk.Label(dest_name_row, text="会社名・団体名", width=22, anchor="w").pack(side="left")
        self.dest_name = tk.StringVar()
        self.dest_name_combo = ttk.Combobox(dest_name_row, textvariable=self.dest_name, width=38)
        self.dest_name_combo.pack(side="left")
        self.dest_name_combo.bind("<KeyRelease>", self._on_dest_name_typed)
        self.dest_name_combo.bind("<<ComboboxSelected>>", self._on_dest_name_selected)
        self.dest_name_combo.bind("<FocusOut>", self._on_dest_name_selected)
        ttk.Button(
            dest_name_row, text="取引先の履歴を管理", command=self.manage_destinations,
        ).pack(side="left", padx=(10, 0))
        ToolTip(
            dest_name_row,
            "▼を押すか、名前の一部を入力すると、過去に入力した取引先の候補が出ます。\n"
            "候補を選ぶと、住所・電話番号なども自動で入力されます。",
        )

        self.dest_zip = self._labeled_entry(sec2, "郵便番号", width=15)
        self.dest_addr = self._labeled_entry(sec2, "住所", width=50)
        self.dest_tel = self._labeled_entry(sec2, "電話番号", width=20)
        self.dest_fax = self._labeled_entry(sec2, "FAX番号（なければ空欄）", width=20)

        # ---- ③ 請求元（自分の情報・印鑑）----
        sec3 = self._section(
            body, "③ 請求元（あなたの情報）",
            "あなた（請求する側）の情報です。請求書の右上（日付の下）にまとめて印字されます。会社印の画像もここで設定します。",
        )
        self.issuer_zip = self._labeled_entry(sec3, "郵便番号", width=15)
        self.issuer_address = self._labeled_entry(sec3, "住所", width=50)
        self.issuer_name = self._labeled_entry(sec3, "事務所の名称", width=40)
        self.issuer_representative = self._labeled_entry(sec3, "代表者名", width=30)
        self.issuer_tel = self._labeled_entry(sec3, "電話番号", width=20)

        self.show_issuer_var = tk.BooleanVar(value=True)
        show_issuer_chk = ttk.Checkbutton(
            sec3, text="この情報を請求書に印字する（チェックを外すと右上に印字されません）",
            variable=self.show_issuer_var, command=self._schedule_preview_update,
        )
        show_issuer_chk.pack(anchor="w", pady=(4, 0))
        ToolTip(show_issuer_chk, "すでに印刷済みの用紙（レターヘッド等）を使う場合など、\nこの情報を印字したくないときはチェックを外してください。")

        seal_row = ttk.Frame(sec3)
        seal_row.pack(anchor="w", pady=4)
        ttk.Label(seal_row, text="会社印（ハンコ）の画像：").grid(row=0, column=0, sticky="w")
        self.seal_path_label = ttk.Label(seal_row, text="（未設定）", foreground="#666")
        self.seal_path_label.grid(row=0, column=1, padx=8, sticky="w")
        ttk.Button(seal_row, text="印鑑画像を選ぶ", command=self.choose_seal).grid(row=0, column=2, padx=6)
        ttk.Button(seal_row, text="設定を消す", command=self.clear_seal).grid(row=0, column=3)
        ToolTip(seal_row, "PNG画像がおすすめです（背景が透明な印影画像がきれいに仕上がります）。\n一度選ぶと次回からも自動的に使われます。")

        # ---- ④ 品目 ----
        sec4 = self._section(body, "④ 請求する内容（品目）", "請求する内容を1行ずつ入力してください。金額は自動計算されます。")

        self.show_note_column_var = tk.BooleanVar(value=True)
        show_note_chk = ttk.Checkbutton(
            sec4, text="請求書の表に「摘要」欄を表示する（チェックを外すと表から摘要欄が消え、他の列が広くなります）",
            variable=self.show_note_column_var, command=self._schedule_preview_update,
        )
        show_note_chk.pack(anchor="w", pady=(0, 6))
        ToolTip(show_note_chk, "摘要欄を使わない場合は、チェックを外すと表がすっきりして見やすくなります。\n入力済みの摘要欄の内容が消えるわけではありません。")

        header_row = ttk.Frame(sec4)
        header_row.pack(anchor="w")
        for text, w in [("日付", 10), ("品名", 26), ("数量", 6), ("単価", 10), ("金額(自動)", 10), ("消費税", 8), ("摘要", 14)]:
            ttk.Label(header_row, text=text, width=w, font=(UI_FONT_FAMILY, 10, "bold")).pack(side="left", padx=2)
        self.items_frame = ttk.Frame(sec4)
        self.items_frame.pack(anchor="w", fill="x")
        self.item_rows = []
        btn_row = ttk.Frame(sec4)
        btn_row.pack(anchor="w", pady=(4, 0))
        ttk.Button(btn_row, text="＋ 行を追加", command=self.add_item_row).pack(side="left")

        total_row = ttk.Frame(sec4)
        total_row.pack(anchor="e", pady=(8, 0))
        ttk.Label(total_row, text="税込合計金額：", font=(UI_FONT_FAMILY, 12, "bold")).pack(side="left")
        self.total_var = tk.StringVar(value="￥0")
        ttk.Label(total_row, textvariable=self.total_var, font=(UI_FONT_FAMILY, 14, "bold"), foreground="#b00020").pack(side="left")

        # ---- ⑤ 備考欄 ----
        sec5 = self._section(body, "⑤ 備考欄（任意）", "伝えたいことがあれば自由に入力してください（空欄でも構いません）。")
        self.remarks_text = tk.Text(sec5, width=80, height=3, font=big_font)
        self.remarks_text.pack(anchor="w")

        # ---- ⑥ 振込先 ----
        sec6 = self._section(body, "⑥ 振込先", "一度入力すれば、次回からも自動的に残ります。")
        self.bank_holder1 = self._labeled_entry(sec6, "名義人（例：〇〇 代表者名）", width=50)
        self.bank_holder2 = self._labeled_entry(sec6, "住所・電話など（任意）", width=50)

        bank_header = ttk.Frame(sec6)
        bank_header.pack(anchor="w", pady=(6, 0))
        for text, w in [("金融機関名", 16), ("支店名", 10), ("店番", 6), ("口座種類", 6), ("口座番号", 12)]:
            ttk.Label(bank_header, text=text, width=w, font=(UI_FONT_FAMILY, 10, "bold")).pack(side="left", padx=2)
        self.banks_frame = ttk.Frame(sec6)
        self.banks_frame.pack(anchor="w", fill="x")
        self.bank_rows = []
        ttk.Button(sec6, text="＋ 振込先を追加", command=self.add_bank_row).pack(anchor="w", pady=(4, 0))

        # ---- ⑦ 領収証（任意） ----
        sec7 = self._section(
            body, "⑦ 領収証（任意）",
            "請求書とあわせて領収証PDFも作りたいときに入力してください。\n"
            "ここを入力しなくても、上の内容で『🧾 領収証PDFを作成する』ボタン（画面いちばん下）が使えます\n"
            "（その場合、領収日は①の発行日、但し書きは「お品代」になります）。",
        )
        self.receipt_same_date_var = tk.BooleanVar(value=True)
        same_date_chk = ttk.Checkbutton(
            sec7, text="領収日は「① 発行日」と同じにする",
            variable=self.receipt_same_date_var, command=self._toggle_receipt_date_fields,
        )
        same_date_chk.pack(anchor="w")

        receipt_date_row = ttk.Frame(sec7)
        receipt_date_row.pack(anchor="w", pady=(4, 8))
        r_today = datetime.date.today()
        self.receipt_year = tk.StringVar(value=str(r_today.year))
        self.receipt_month = tk.StringVar(value=str(r_today.month))
        self.receipt_day = tk.StringVar(value=str(r_today.day))
        self.receipt_year_entry = ttk.Entry(receipt_date_row, textvariable=self.receipt_year, width=6)
        self.receipt_year_entry.grid(row=0, column=0)
        ttk.Label(receipt_date_row, text="年（西暦）").grid(row=0, column=1, padx=(2, 10))
        self.receipt_month_entry = ttk.Entry(receipt_date_row, textvariable=self.receipt_month, width=4)
        self.receipt_month_entry.grid(row=0, column=2)
        ttk.Label(receipt_date_row, text="月").grid(row=0, column=3, padx=(2, 10))
        self.receipt_day_entry = ttk.Entry(receipt_date_row, textvariable=self.receipt_day, width=4)
        self.receipt_day_entry.grid(row=0, column=4)
        ttk.Label(receipt_date_row, text="日").grid(row=0, column=5, padx=(2, 0))
        ToolTip(receipt_date_row, "実際にお金を受け取った（受け取る予定の）日付を入力してください。")

        self.receipt_note = self._labeled_entry(sec7, "但し書き（〜として）", width=40)
        self.receipt_note.set("お品代")

        self._toggle_receipt_date_fields()

        # ---- 作成ボタン ----
        ttk.Separator(self.root).pack(fill="x")
        bottom = ttk.Frame(self.root, padding=14)
        bottom.pack(fill="x")
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=1)

        invoice_col = ttk.Frame(bottom)
        invoice_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        make_btn = tk.Button(
            invoice_col, text="📄 請求書PDFを作成する", font=(UI_FONT_FAMILY, 14, "bold"),
            bg="#1a73e8", fg="white", activebackground="#1558b0", activeforeground="white",
            height=2, command=self.on_create_pdf,
        )
        make_btn.pack(fill="x")
        ttk.Label(
            invoice_col,
            text="ボタンを押すと、PDFの保存場所を選ぶ画面が開きます。分かりやすい場所（デスクトップなど）を選んでください。",
            foreground="#666", wraplength=260, justify="left",
        ).pack(pady=(4, 0), fill="x")

        receipt_col = ttk.Frame(bottom)
        receipt_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        receipt_btn = tk.Button(
            receipt_col, text="🧾 領収証PDFを作成する", font=(UI_FONT_FAMILY, 14, "bold"),
            bg="#188038", fg="white", activebackground="#0f6b2c", activeforeground="white",
            height=2, command=self.on_create_receipt,
        )
        receipt_btn.pack(fill="x")
        ttk.Label(
            receipt_col,
            text="今入力している内容（宛先・金額・発行元など）をもとに、領収証PDFを作成します。請求書PDFとは別に、必要な分だけ作成できます。",
            foreground="#666", wraplength=260, justify="left",
        ).pack(pady=(4, 0), fill="x")

        # ---- フッター（バージョン・クレジット表記） ----
        ttk.Separator(self.root).pack(fill="x")
        footer = ttk.Frame(self.root, padding=(10, 6))
        footer.pack(fill="x")
        ttk.Label(
            footer,
            text=f"{APP_VERSION}　|　開発：{APP_CREDIT}　|　サポート：{APP_SUPPORT_EMAIL}",
            foreground="#999", font=(UI_FONT_FAMILY, 9),
            anchor="center", justify="center",
        ).pack(fill="x")

        # 初期行
        for _ in range(3):
            self.add_item_row()
        for _ in range(1):
            self.add_bank_row()

    # ---------------------------------------------------------- プレビュー
    def _build_preview_pane(self, parent):
        header = ttk.Frame(parent, padding=(10, 10, 10, 4))
        header.pack(fill="x")
        ttk.Label(header, text="📄 プレビュー", font=(UI_FONT_FAMILY, 14, "bold")).pack(side="left")

        if not PDF_PREVIEW_AVAILABLE:
            ttk.Label(
                parent,
                text=(
                    "プレビュー機能を使うには、追加のライブラリが必要です。\n\n"
                    "コマンドプロンプト（またはPowerShell）で、このフォルダに移動してから\n"
                    "次のコマンドを実行してください：\n\n"
                    "    pip install -r requirements.txt\n\n"
                    "（PyMuPDF というライブラリが必要です）\n\n"
                    "インストール後、このツールを開き直すとプレビューが使えるようになります。\n"
                    "※ プレビューが使えなくても、PDFの作成自体は通常通り行えます。"
                ),
                foreground="#a00", wraplength=420, justify="left", padding=20,
            ).pack(fill="both", expand=True)
            return

        self.preview_doc_var = tk.StringVar(value="invoice")
        ttk.Radiobutton(
            header, text="請求書", value="invoice", variable=self.preview_doc_var,
            command=self._update_preview,
        ).pack(side="left", padx=(16, 4))
        ttk.Radiobutton(
            header, text="領収証", value="receipt", variable=self.preview_doc_var,
            command=self._update_preview,
        ).pack(side="left")
        ttk.Button(header, text="🔄 今すぐ更新", command=self._update_preview).pack(side="right")

        self.preview_status_var = tk.StringVar(value="入力すると自動でプレビューされます")
        ttk.Label(
            parent, textvariable=self.preview_status_var, foreground="#666",
        ).pack(fill="x", padx=10, anchor="w")

        preview_frame = ttk.Frame(parent, padding=(10, 4, 10, 10))
        preview_frame.pack(fill="both", expand=True)
        self.preview_canvas = tk.Canvas(preview_frame, bg="#d9d9d9", highlightthickness=0)
        preview_vscroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview_canvas.yview)
        self.preview_canvas.configure(yscrollcommand=preview_vscroll.set)
        self.preview_canvas.pack(side="left", fill="both", expand=True)
        preview_vscroll.pack(side="right", fill="y")

        self.preview_image_label = tk.Label(
            self.preview_canvas, bg="white",
            text="ここに請求書／領収証のプレビューが表示されます",
            fg="#999", font=(UI_FONT_FAMILY, 11),
        )
        self.preview_canvas.create_window((0, 0), window=self.preview_image_label, anchor="nw")

        # 右カラムの幅が変わったとき（起動直後・分割線をドラッグしたときなど）も
        # プレビューを最新の幅に合わせて更新する
        self.preview_canvas.bind("<Configure>", self._schedule_preview_update)

        # プレビュー欄の上でマウスホイールを回したときは、左側の入力欄ではなく
        # プレビュー自身がスクロールするようにする
        def _on_preview_mousewheel(event):
            self.preview_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        self.preview_canvas.bind("<MouseWheel>", _on_preview_mousewheel)
        self.preview_image_label.bind("<MouseWheel>", _on_preview_mousewheel)

    def _schedule_preview_update(self, _event=None):
        if not PDF_PREVIEW_AVAILABLE:
            return
        if self._preview_after_id is not None:
            try:
                self.root.after_cancel(self._preview_after_id)
            except Exception:
                pass
        self._preview_after_id = self.root.after(600, self._update_preview)

    def _update_preview(self):
        self._preview_after_id = None
        if not PDF_PREVIEW_AVAILABLE:
            return
        try:
            if self.preview_doc_var.get() == "receipt":
                if self.receipt_same_date_var.get():
                    y, m, d = int(self.date_year.get()), int(self.date_month.get()), int(self.date_day.get())
                else:
                    y, m, d = int(self.receipt_year.get()), int(self.receipt_month.get()), int(self.receipt_day.get())
                doc_date = datetime.date(y, m, d)
                data = self._collect_receipt_data(doc_date)
                from pdf_builder import build_receipt_pdf as build_fn
            else:
                y, m, d = int(self.date_year.get()), int(self.date_month.get()), int(self.date_day.get())
                doc_date = datetime.date(y, m, d)
                data = self._collect_invoice_data(doc_date)
                from pdf_builder import build_invoice_pdf as build_fn

            buf = BytesIO()
            build_fn(buf, data)

            doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
            page = doc[0]
            target_w = self.preview_canvas.winfo_width()
            if target_w < 100:
                target_w = 700
            zoom = max(0.5, min((target_w - 24) / page.rect.width, 3.0))
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            ppm_bytes = pix.tobytes("ppm")
            doc.close()

            photo = tk.PhotoImage(data=ppm_bytes)
            self._preview_photo = photo  # 参照を保持しないとGCで画像が消えてしまう
            self.preview_image_label.config(image=photo, text="", bg="white")
            self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))
            self.preview_status_var.set(
                "最終更新：" + datetime.datetime.now().strftime("%H:%M:%S")
            )
        except Exception:
            self.preview_status_var.set("入力内容を確認してください（プレビュー未更新）")

    def _section(self, parent, title, help_text):
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.pack(fill="x", pady=8)
        if help_text:
            ttk.Label(frame, text=help_text, foreground="#666", wraplength=880).pack(anchor="w", pady=(0, 6))
        return frame

    def _labeled_entry(self, parent, label, width=30):
        row = ttk.Frame(parent)
        row.pack(anchor="w", pady=2, fill="x")
        ttk.Label(row, text=label, width=22, anchor="w").pack(side="left")
        var = tk.StringVar()
        ttk.Entry(row, textvariable=var, width=width).pack(side="left")
        return var

    # ---------------------------------------------------------- 行操作
    def add_item_row(self):
        row = ItemRow(self.items_frame, self.recalc_total, self.remove_item_row)
        row.frame.pack(anchor="w", pady=1)
        self.item_rows.append(row)
        self._schedule_preview_update()

    def remove_item_row(self, row):
        if len(self.item_rows) <= 1:
            messagebox.showinfo("お知らせ", "最低1行は必要です。")
            return
        row.frame.destroy()
        self.item_rows.remove(row)
        self.recalc_total()
        self._schedule_preview_update()

    def add_bank_row(self):
        row = BankRow(self.banks_frame, self.remove_bank_row)
        row.frame.pack(anchor="w", pady=1)
        self.bank_rows.append(row)
        self._schedule_preview_update()

    def remove_bank_row(self, row):
        if len(self.bank_rows) <= 1:
            messagebox.showinfo("お知らせ", "最低1行は必要です。")
            return
        row.frame.destroy()
        self.bank_rows.remove(row)
        self._schedule_preview_update()

    def recalc_total(self):
        total = sum(r.get_amount() + r.get_tax() for r in self.item_rows)
        self.total_var.set(format_yen(total))

    def _toggle_receipt_date_fields(self):
        state = "disabled" if self.receipt_same_date_var.get() else "normal"
        for e in (self.receipt_year_entry, self.receipt_month_entry, self.receipt_day_entry):
            e.config(state=state)
        self._schedule_preview_update()

    # ---------------------------------------------------------- 設定読み込み
    def _load_defaults_into_form(self):
        cfg = self.cfg
        if cfg.get("seal_image_path") and os.path.exists(cfg["seal_image_path"]):
            self.seal_path_label.config(text=os.path.basename(cfg["seal_image_path"]))
        self.issuer_zip.set(cfg.get("issuer_zip", ""))
        self.issuer_address.set(cfg.get("issuer_address", ""))
        self.issuer_name.set(cfg.get("issuer_name", ""))
        self.issuer_representative.set(cfg.get("issuer_representative", ""))
        self.issuer_tel.set(cfg.get("issuer_tel", ""))
        self.show_issuer_var.set(bool(cfg.get("show_issuer_block", True)))
        self.show_note_column_var.set(bool(cfg.get("show_note_column", True)))
        self.bank_holder1.set(cfg.get("bank_holder_line1", ""))
        self.bank_holder2.set(cfg.get("bank_holder_line2", ""))
        self.remarks_text.insert("1.0", cfg.get("remarks_default", ""))
        self._refresh_destination_list()

        banks = cfg.get("banks") or []
        if banks:
            # 既存の初期行をクリアしてから読み込む
            for r in list(self.bank_rows):
                r.frame.destroy()
            self.bank_rows.clear()
            for b in banks:
                if not any(b.values()):
                    continue
                row = BankRow(self.banks_frame, self.remove_bank_row)
                row.frame.pack(anchor="w", pady=1)
                row.name_var.set(b.get("name", ""))
                row.branch_var.set(b.get("branch", ""))
                row.code_var.set(b.get("code", ""))
                row.type_var.set(b.get("type", "普通"))
                row.number_var.set(b.get("number", ""))
                self.bank_rows.append(row)

        self._schedule_preview_update()

    def _save_current_settings(self):
        self.cfg["issuer_zip"] = self.issuer_zip.get().strip()
        self.cfg["issuer_address"] = self.issuer_address.get().strip()
        self.cfg["issuer_name"] = self.issuer_name.get().strip()
        self.cfg["issuer_representative"] = self.issuer_representative.get().strip()
        self.cfg["issuer_tel"] = self.issuer_tel.get().strip()
        self.cfg["show_issuer_block"] = bool(self.show_issuer_var.get())
        self.cfg["show_note_column"] = bool(self.show_note_column_var.get())
        self.cfg["bank_holder_line1"] = self.bank_holder1.get().strip()
        self.cfg["bank_holder_line2"] = self.bank_holder2.get().strip()
        self.cfg["remarks_default"] = self.remarks_text.get("1.0", "end").strip()
        self.cfg["banks"] = [r.as_dict() for r in self.bank_rows if not r.is_blank()]
        self._remember_current_destination()
        save_config(self.cfg)

    # ---------------------------------------------------------- 取引先（宛先）の履歴
    def _remember_current_destination(self):
        """今入力されている宛先を、次回以降も選べるように履歴へ保存する。
        同じ名前がすでにあれば、最新の内容で上書きしたうえで一番上に移動する。"""
        name = self.dest_name.get().strip()
        if not name:
            return
        entry = {
            "name": name,
            "zip": self.dest_zip.get().strip(),
            "addr": self.dest_addr.get().strip(),
            "tel": self.dest_tel.get().strip(),
            "fax": self.dest_fax.get().strip(),
        }
        destinations = [d for d in self.cfg.get("destinations", []) if d.get("name") != name]
        destinations.insert(0, entry)
        self.cfg["destinations"] = destinations[:MAX_DESTINATION_HISTORY]
        self._refresh_destination_list()

    def _refresh_destination_list(self):
        names = [d.get("name", "") for d in self.cfg.get("destinations", [])]
        self.dest_name_combo["values"] = names

    def _on_dest_name_typed(self, event=None):
        # カーソル移動・選択確定などのキーはそのまま素通りさせる
        if event is not None and event.keysym in (
            "Up", "Down", "Return", "Escape", "Tab", "Shift_L", "Shift_R",
        ):
            return
        typed = self.dest_name.get()
        all_names = [d.get("name", "") for d in self.cfg.get("destinations", [])]
        if typed:
            matches = [n for n in all_names if typed.lower() in n.lower()]
        else:
            matches = all_names
        self.dest_name_combo["values"] = matches
        if typed and matches:
            try:
                # 候補が絞り込まれたら、プルダウンを自動で開いて見せる
                self.dest_name_combo.tk.call("ttk::combobox::Post", str(self.dest_name_combo))
                self.dest_name_combo.focus_set()
                self.dest_name_combo.icursor("end")
            except Exception:
                pass  # 環境によりプルダウンの自動表示ができなくても、候補の絞り込み自体は機能する

    def _on_dest_name_selected(self, event=None):
        name = self.dest_name.get().strip()
        for d in self.cfg.get("destinations", []):
            if d.get("name") == name:
                self.dest_zip.set(d.get("zip", ""))
                self.dest_addr.set(d.get("addr", ""))
                self.dest_tel.set(d.get("tel", ""))
                self.dest_fax.set(d.get("fax", ""))
                break
        self._schedule_preview_update()

    def manage_destinations(self):
        win = tk.Toplevel(self.root)
        win.title("取引先の履歴を管理")
        win.geometry("420x440")
        ttk.Label(
            win,
            text="これまでに入力した取引先（宛先）の一覧です。\n"
            "使わないもの・入力を間違えたものは、選んで削除できます。",
            foreground="#666", wraplength=380, justify="left",
        ).pack(padx=12, pady=(12, 6), anchor="w")

        list_frame = ttk.Frame(win)
        list_frame.pack(fill="both", expand=True, padx=12)
        listbox = tk.Listbox(list_frame, font=(UI_FONT_FAMILY, 11))
        listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        scroll.pack(side="right", fill="y")
        listbox.config(yscrollcommand=scroll.set)

        def _reload():
            listbox.delete(0, "end")
            for d in self.cfg.get("destinations", []):
                listbox.insert("end", d.get("name", ""))

        _reload()

        def _delete_selected():
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("お知らせ", "削除する取引先を、リストから選んでください。")
                return
            name = listbox.get(sel[0])
            if not messagebox.askyesno("確認", f"「{name}」を履歴から削除しますか？\n（現在入力中の内容は消えません）"):
                return
            self.cfg["destinations"] = [d for d in self.cfg.get("destinations", []) if d.get("name") != name]
            save_config(self.cfg)
            self._refresh_destination_list()
            _reload()

        btn_row = ttk.Frame(win)
        btn_row.pack(fill="x", padx=12, pady=12)
        ttk.Button(btn_row, text="選んだ取引先を削除", command=_delete_selected).pack(side="left")
        ttk.Button(btn_row, text="閉じる", command=win.destroy).pack(side="right")

    # ---------------------------------------------------------- 印鑑画像
    def choose_seal(self):
        path = filedialog.askopenfilename(
            title="会社印（ハンコ）の画像ファイルを選んでください",
            filetypes=[("画像ファイル", "*.png *.jpg *.jpeg *.gif *.bmp"), ("すべてのファイル", "*.*")],
        )
        if path:
            self.cfg["seal_image_path"] = path
            self.seal_path_label.config(text=os.path.basename(path))
            save_config(self.cfg)
            messagebox.showinfo("設定完了", "印鑑画像を設定しました。\n次回からも自動的に使われます。")
            self._schedule_preview_update()

    def clear_seal(self):
        self.cfg["seal_image_path"] = ""
        self.seal_path_label.config(text="（未設定）")
        save_config(self.cfg)
        self._schedule_preview_update()

    # ---------------------------------------------------------- ヘルプ
    def show_help(self):
        win = tk.Toplevel(self.root)
        win.title("使い方ヘルプ")
        win.geometry("560x560")
        text = tk.Text(win, wrap="word", font=(UI_FONT_FAMILY, 11), padx=12, pady=12)
        text.insert("1.0", HELP_TEXT)
        text.config(state="disabled")
        text.pack(fill="both", expand=True)
        ttk.Button(win, text="閉じる", command=win.destroy).pack(pady=8)

    # ---------------------------------------------------------- アップデート
    def check_for_updates(self):
        import updater

        if not updater.is_configured(UPDATE_MANIFEST_URL):
            messagebox.showinfo(
                "お知らせ",
                "アップデート機能はまだ準備中です。\n開発者にご確認ください。",
            )
            return

        self.root.config(cursor="watch")
        self.root.update()
        try:
            info = updater.check_for_update(UPDATE_MANIFEST_URL)
        except updater.UpdateError as e:
            messagebox.showwarning(
                "確認できませんでした",
                "アップデートの確認ができませんでした。\n"
                "インターネットに接続されているかご確認のうえ、\n"
                "もう一度お試しください。\n\n"
                f"（技術情報）{e}",
            )
            return
        finally:
            self.root.config(cursor="")

        remote_v = info.get("version", "0")
        notes = info.get("notes", "")
        if updater.parse_version(remote_v) <= updater.parse_version(APP_VERSION_NUM):
            messagebox.showinfo("お知らせ", f"お使いの{APP_VERSION}は最新です。")
            return

        if getattr(sys, "frozen", False):
            # exe/deb版は、ZIPを上書きする今の更新方式が使えない
            # （フォルダの中身をまるごと入れ替える前提の仕組みのため）。
            # 新しいインストーラーをダウンロードしてもらうよう案内する。
            msg = f"新しいバージョン（{remote_v}）が公開されています。\n"
            if notes:
                msg += f"\n【更新内容】\n{notes}\n"
            msg += (
                "\nこの版（exe/deb）は自動更新に対応していないため、"
                "配布ページから新しいインストーラーをダウンロードして、"
                "入れ直してください。"
            )
            messagebox.showinfo("新しいバージョンがあります", msg)
            return

        msg = f"新しいバージョン（{remote_v}）が見つかりました。\n今すぐ更新しますか？"
        if notes:
            msg += f"\n\n【更新内容】\n{notes}"
        if not messagebox.askyesno("アップデートがあります", msg):
            return

        self.root.config(cursor="watch")
        self.root.update()
        try:
            updater.download_and_apply_update(info["zip_url"], APP_DIR)
        except updater.UpdateError as e:
            messagebox.showerror(
                "更新に失敗しました",
                "アップデートの適用中に問題が発生しました。\n"
                "お手数ですが、開発者にご連絡ください。\n\n"
                f"（技術情報）{e}",
            )
            return
        finally:
            self.root.config(cursor="")

        messagebox.showinfo(
            "更新が完了しました",
            "アップデートが完了しました。\n"
            "変更を反映するため、いったんこのツールを閉じます。\n"
            "閉じたあと、もう一度デスクトップのアイコンから開き直してください。",
        )
        self.root.destroy()

    # ---------------------------------------------------------- 入力チェック
    def _validate(self):
        errors = []
        try:
            y, m, d = int(self.date_year.get()), int(self.date_month.get()), int(self.date_day.get())
            datetime.date(y, m, d)
        except Exception:
            errors.append("『① 発行日』が正しく入力されていません。年・月・日は数字で入力してください。")

        if not self.dest_name.get().strip():
            errors.append("『② 宛先』の会社名・団体名が入力されていません。")

        any_item = False
        for i, row in enumerate(self.item_rows, start=1):
            if row.is_blank():
                continue
            any_item = True
            if row.price_var.get().strip():
                try:
                    float(row.price_var.get())
                except ValueError:
                    errors.append(f"『④ 品目』{i}行目の単価は数字で入力してください。")
            if row.qty_var.get().strip():
                try:
                    float(row.qty_var.get())
                except ValueError:
                    errors.append(f"『④ 品目』{i}行目の数量は数字で入力してください。")
        if not any_item:
            errors.append("『④ 品目』が1件も入力されていません。少なくとも1行は入力してください。")

        seal = self.cfg.get("seal_image_path")
        if seal and not os.path.exists(seal):
            errors.append("設定されている印鑑画像が見つかりません。もう一度『印鑑画像を選ぶ』からやり直してください。")

        return errors

    # ---------------------------------------------------------- データ収集（PDF作成・プレビュー共通）
    def _collect_invoice_data(self, issue_date):
        items = [r.as_dict() for r in self.item_rows if not r.is_blank()]
        total = sum(r.get_amount() + r.get_tax() for r in self.item_rows)
        return {
            "issue_date": issue_date,
            "invoice_number": self.invoice_number.get().strip(),
            "dest_name": self.dest_name.get().strip(),
            "dest_zip": self.dest_zip.get().strip(),
            "dest_addr": self.dest_addr.get().strip(),
            "dest_tel": self.dest_tel.get().strip(),
            "dest_fax": self.dest_fax.get().strip(),
            "issuer_zip": self.issuer_zip.get().strip(),
            "issuer_address": self.issuer_address.get().strip(),
            "issuer_name": self.issuer_name.get().strip(),
            "issuer_representative": self.issuer_representative.get().strip(),
            "issuer_tel": self.issuer_tel.get().strip(),
            "show_issuer_block": bool(self.show_issuer_var.get()),
            "show_note_column": bool(self.show_note_column_var.get()),
            "seal_path": self.cfg.get("seal_image_path", ""),
            "items": items,
            "total": total,
            "remarks": self.remarks_text.get("1.0", "end").strip(),
            "bank_holder1": self.bank_holder1.get().strip(),
            "bank_holder2": self.bank_holder2.get().strip(),
            "banks": [r.as_dict() for r in self.bank_rows if not r.is_blank()],
        }

    def _collect_receipt_data(self, receipt_date):
        items = [r.as_dict() for r in self.item_rows if not r.is_blank()]
        total = sum(r.get_amount() + r.get_tax() for r in self.item_rows)
        tax_total = sum(r.get_tax() for r in self.item_rows)
        return {
            "issue_date": receipt_date,
            "invoice_number": self.invoice_number.get().strip(),
            "dest_name": self.dest_name.get().strip(),
            "dest_zip": self.dest_zip.get().strip(),
            "dest_addr": self.dest_addr.get().strip(),
            "dest_tel": self.dest_tel.get().strip(),
            "dest_fax": self.dest_fax.get().strip(),
            "items": items,
            "show_note_column": bool(self.show_note_column_var.get()),
            "total": total,
            "tax_total": tax_total,
            "remarks": self.receipt_note.get().strip() or "お品代",
            "issuer_zip": self.issuer_zip.get().strip(),
            "issuer_address": self.issuer_address.get().strip(),
            "issuer_name": self.issuer_name.get().strip(),
            "issuer_representative": self.issuer_representative.get().strip(),
            "issuer_tel": self.issuer_tel.get().strip(),
            "show_issuer_block": bool(self.show_issuer_var.get()),
            "seal_path": self.cfg.get("seal_image_path", ""),
        }

    # ---------------------------------------------------------- PDF作成
    def on_create_pdf(self):
        errors = self._validate()
        if errors:
            messagebox.showwarning("入力内容を確認してください", "\n\n".join(errors))
            return

        self._save_current_settings()

        y, m, d = int(self.date_year.get()), int(self.date_month.get()), int(self.date_day.get())
        issue_date = datetime.date(y, m, d)
        data = self._collect_invoice_data(issue_date)

        default_name = f"請求書_{issue_date.strftime('%Y%m%d')}_{data['dest_name'] or '宛先未設定'}.pdf"
        save_path = self._pick_save_path("請求書PDFの保存先を選んでください", default_name)
        if not save_path:
            return

        try:
            from pdf_builder import build_invoice_pdf
            build_invoice_pdf(save_path, data)
        except Exception:
            err = traceback.format_exc()
            messagebox.showerror(
                "PDFの作成に失敗しました",
                "申し訳ありません、PDFの作成中に問題が発生しました。\n"
                "入力内容をもう一度ご確認のうえ、お試しください。\n\n"
                "（技術情報）\n" + err[-800:],
            )
            return

        self.cfg["last_save_dir"] = os.path.dirname(save_path)
        save_config(self.cfg)

        self._offer_open_file(save_path, "請求書")

    # ---------------------------------------------------------- 領収証作成
    def _validate_receipt(self):
        errors = []
        if not self.dest_name.get().strip():
            errors.append("『② 宛先』の会社名・団体名が入力されていません。")

        total = sum(r.get_amount() + r.get_tax() for r in self.item_rows)
        if total <= 0:
            errors.append("金額が入力されていません。『④ 品目』欄に内容を入力してください。")

        if not self.receipt_same_date_var.get():
            try:
                y, m, d = int(self.receipt_year.get()), int(self.receipt_month.get()), int(self.receipt_day.get())
                datetime.date(y, m, d)
            except Exception:
                errors.append("『⑦ 領収証』の領収日が正しく入力されていません。年・月・日は数字で入力してください。")

        seal = self.cfg.get("seal_image_path")
        if seal and not os.path.exists(seal):
            errors.append("設定されている印鑑画像が見つかりません。もう一度『印鑑画像を選ぶ』からやり直してください。")

        return errors

    def on_create_receipt(self):
        errors = self._validate_receipt()
        if errors:
            messagebox.showwarning("入力内容を確認してください", "\n\n".join(errors))
            return

        self._save_current_settings()

        if self.receipt_same_date_var.get():
            y, m, d = int(self.date_year.get()), int(self.date_month.get()), int(self.date_day.get())
        else:
            y, m, d = int(self.receipt_year.get()), int(self.receipt_month.get()), int(self.receipt_day.get())
        receipt_date = datetime.date(y, m, d)
        data = self._collect_receipt_data(receipt_date)

        default_name = f"領収証_{receipt_date.strftime('%Y%m%d')}_{data['dest_name'] or '宛先未設定'}.pdf"
        save_path = self._pick_save_path("領収証PDFの保存先を選んでください", default_name)
        if not save_path:
            return

        try:
            from pdf_builder import build_receipt_pdf
            build_receipt_pdf(save_path, data)
        except Exception:
            err = traceback.format_exc()
            messagebox.showerror(
                "PDFの作成に失敗しました",
                "申し訳ありません、領収証PDFの作成中に問題が発生しました。\n"
                "入力内容をもう一度ご確認のうえ、お試しください。\n\n"
                "（技術情報）\n" + err[-800:],
            )
            return

        self.cfg["last_save_dir"] = os.path.dirname(save_path)
        save_config(self.cfg)

        self._offer_open_file(save_path, "領収証")

    # ---------------------------------------------------------- 保存・オープン共通処理
    def _pick_save_path(self, title, default_name):
        default_dir = self.cfg.get("last_save_dir") or os.path.expanduser("~/Desktop")
        if not os.path.isdir(default_dir):
            default_dir = os.path.expanduser("~")
        # ファイル名に使えない文字を除去
        for ch in '\\/:*?"<>|':
            default_name = default_name.replace(ch, "")
        return filedialog.asksaveasfilename(
            title=title,
            initialdir=default_dir,
            initialfile=default_name,
            defaultextension=".pdf",
            filetypes=[("PDFファイル", "*.pdf")],
        )

    def _offer_open_file(self, save_path, doc_label):
        if messagebox.askyesno("完成しました", f"{doc_label}PDFを作成しました。\n\n{save_path}\n\nこのファイルを開きますか？"):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(save_path)  # noqa
                elif sys.platform == "darwin":
                    os.system(f'open "{save_path}"')
                else:
                    os.system(f'xdg-open "{save_path}"')
            except Exception:
                messagebox.showinfo("お知らせ", "ファイルは作成されましたが、自動で開けませんでした。\n保存先フォルダから開いてください。")


def main():
    _ensure_bundled_font_on_linux()
    root = tk.Tk()
    global UI_FONT_FAMILY
    UI_FONT_FAMILY = _pick_ui_font_family(root)
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    app = InvoiceApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 予期しないエラーでも、真っ黒な画面ではなく分かるメッセージを出す
        err = traceback.format_exc()
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "エラーが発生しました",
                "アプリの起動中に問題が発生しました。お手数ですが、開発者にご連絡ください。\n\n" + err[-1000:],
            )
        except Exception:
            print(err)
