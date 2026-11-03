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


def _setup_linux_input_method():
    """Linuxで日本語入力（IME）がこの画面につながるようにする。Tk() を作る前に呼ぶこと。

    Tkinter は X Input Method（XIM）経由でしかIMEとつながらず、接続先のIMEは
    XMODIFIERS 環境変数（例：@im=fcitx）で指定する決まりになっている。
    GNOMEなどは自動で設定してくれるが、WSLや一部のデスクトップでは空のままで、
    その場合は日本語が打てず英字しか入らない。そこで未設定のときだけ、
    GTK_IM_MODULE などの設定や、実際に動いているIMEから推測して補う（失敗しても無視）。
    """
    if not sys.platform.startswith("linux") or os.environ.get("XMODIFIERS"):
        return
    try:
        hint = " ".join(
            os.environ.get(k, "") for k in ("GTK_IM_MODULE", "QT_IM_MODULE", "INPUT_METHOD")
        ).strip().lower()
        if not hint:
            # 動いているプロセス名から探す（fcitx5・fcitx・ibus-daemon・uim-xim など）
            names = []
            for pid in os.listdir("/proc"):
                if pid.isdigit():
                    try:
                        with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
                            names.append(f.read().strip())
                    except Exception:
                        pass
            hint = " ".join(names).lower()
        # fcitx5 も XIM の接続名は「fcitx」
        for key, im_name in (("fcitx", "fcitx"), ("ibus", "ibus"), ("uim", "uim")):
            if key in hint:
                os.environ["XMODIFIERS"] = f"@im={im_name}"
                return
    except Exception:
        pass


def _match_ime_font_to_widget(event):
    """Windowsで、日本語の変換中の文字を入力欄と同じフォント・大きさで表示させる。

    Tk は変換中の文字のフォントを IME に伝えないため、IME が自分の既定の書体で
    描いてしまい、確定前と確定後で見た目が大きく変わる。そこで入力欄にフォーカスが
    来るたびに、その欄のフォントを ImmSetCompositionFontW で IME に伝える
    （失敗しても入力自体には影響しないので無視する）。"""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        from ctypes import wintypes

        w = event.widget
        if not isinstance(w, tk.Misc) or w.winfo_class() not in (
            "TEntry", "Entry", "TCombobox", "Text", "TSpinbox", "Spinbox",
        ):
            return
        actual = w.tk.splitlist(w.tk.call("font", "actual", w.cget("font") or "TkTextFont"))
        actual = dict(zip(actual[::2], actual[1::2]))
        size = int(actual["-size"])
        # 正の値はポイント、負の値はピクセル（Tkの決まり）
        px = -size if size < 0 else size * w.winfo_fpixels("1i") / 72

        class LOGFONTW(ctypes.Structure):
            _fields_ = [
                ("lfHeight", wintypes.LONG), ("lfWidth", wintypes.LONG),
                ("lfEscapement", wintypes.LONG), ("lfOrientation", wintypes.LONG),
                ("lfWeight", wintypes.LONG), ("lfItalic", wintypes.BYTE),
                ("lfUnderline", wintypes.BYTE), ("lfStrikeOut", wintypes.BYTE),
                ("lfCharSet", wintypes.BYTE), ("lfOutPrecision", wintypes.BYTE),
                ("lfClipPrecision", wintypes.BYTE), ("lfQuality", wintypes.BYTE),
                ("lfPitchAndFamily", wintypes.BYTE), ("lfFaceName", wintypes.WCHAR * 32),
            ]

        lf = LOGFONTW()
        lf.lfHeight = -round(px)
        lf.lfWeight = 700 if actual.get("-weight") == "bold" else 400
        lf.lfCharSet = 128  # SHIFTJIS_CHARSET
        lf.lfFaceName = actual["-family"][:31]

        imm32 = ctypes.windll.imm32
        imm32.ImmGetContext.argtypes = [wintypes.HWND]
        imm32.ImmGetContext.restype = wintypes.HANDLE
        imm32.ImmSetCompositionFontW.argtypes = [wintypes.HANDLE, ctypes.POINTER(LOGFONTW)]
        imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
        hwnd = w.winfo_id()
        himc = imm32.ImmGetContext(hwnd)
        if himc:
            imm32.ImmSetCompositionFontW(himc, ctypes.byref(lf))
            imm32.ImmReleaseContext(hwnd, himc)
    except Exception:
        pass


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


APP_VERSION_NUM = "1.5"
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
    "doc_format": "standard",  # PDFの書式。"standard"＝標準、"classic"＝以前のシステムと同じ書式
    "destinations": [],  # 過去に入力した取引先（宛先）の履歴。新しい順。
}

# PDFの書式（設定ファイルに保存する値 → 画面に出す名前）
DOC_FORMAT_LABELS = {
    "standard": "モダン",
    "classic": "クラシック",
}

# 「ダミーデータを下記の全空欄に入力」ボタンで入れる、出力テスト用の内容。
# 品目は合計が5万円を超えるようにして、領収証の収入印紙欄も確認できるようにしている。
DUMMY_FIELDS = {
    "invoice_number": "DUMMY-0001",
    "dest_name": "ダミー株式会社",
    "dest_zip": "100-0001",
    "dest_addr": "東京都千代田区ダミー町1-2-3",
    "dest_tel": "03-0000-0000",
    "dest_fax": "03-0000-0001",
    "issuer_zip": "150-0000",
    "issuer_address": "東京都渋谷区テスト町4-5-6",
    "issuer_name": "テスト商店街振興組合",
    "issuer_representative": "代表理事 見本 太郎",
    "issuer_tel": "03-1111-2222",
    "issuer_fax": "03-1111-2223",
    "bank_holder1": "テスト商店街振興組合 代表理事 見本太郎",
    "bank_holder2": "東京都渋谷区テスト町4-5-6　電話03-1111-2222",
}
DUMMY_REMARKS = "これは出力テスト用のダミーデータです。"
# (日付, 品名, 数量, 単価, 消費税, 摘要)
DUMMY_ITEMS = [
    ("10月1日", "賦課金 R8.10〜R9.3月", "6", "1800", "", ""),
    ("10月1日", "準組合費", "12", "1500", "", "令和8.11〜9.10月"),
    ("10月15日", "イベント協賛金", "1", "50000", "5000", "テスト用"),
]
# (金融機関名, 支店名, 店番, 口座種類, 口座番号)
DUMMY_BANKS = [
    ("ダミー信用金庫", "本店", "001", "普通", "1234567"),
    ("テスト銀行", "駅前", "123", "当座", "7654321"),
]
DUMMY_SEAL_PATH = os.path.join(_USER_DATA_DIR, "dummy_seal.png")
DUMMY_BUTTON_FILL = "🧪 ダミーデータを下記の全空欄に入力"
DUMMY_BUTTON_CLEAR = "🧹 入力したダミーデータを消して空欄に戻す"
DUMMY_STATUS_IDLE = "出力テスト用です。空いている欄だけに入力します（入力済みの欄はそのまま）。"
DUMMY_STATUS_ACTIVE = (
    "※ ダミーデータ入力中：設定・取引先の履歴は保存されません。もう一度押すと消せます。"
)

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

  Q. 以前のシステムと同じ形の請求書・領収書にしたい
  A. 画面いちばん上の「PDFの書式」で「クラシック」を
     選んでください。請求書・領収証のどちらのボタンにも効きます。
     選んだ書式は、次にこのアプリを開いたときも残ります。

  Q. 請求書と領収証を一度に作りたい
  A. 画面いちばん下の「📑 請求書・領収証を一括作成」ボタンを押すと、
     保存するフォルダを1回選ぶだけで、両方のPDFがまとめて作成されます。

  Q. 印刷や見た目の確認だけしたい（テスト用のデータで試したい）
  A. 入力欄のいちばん上にある「🧪 ダミーデータを下記の全空欄に入力」
     ボタンを押すと、空いている欄に「ダミー株式会社」などの見本の
     内容が入ります（入力済みの欄はそのまま）。会社印が未設定なら
     「見本之印」という仮の印影も使われます。
     ダミーデータを入れている間は、設定や取引先の履歴は保存されないので、
     本番の情報が書き換わる心配はありません。
     もう一度同じボタン（「🧹 入力したダミーデータを消して空欄に戻す」）を
     押すと、ダミーで入れた欄だけが空欄に戻ります（あとから書き換えた欄は残ります）。

  Q. 保存する前に、出来上がりを見たい
  A. 画面右側に「プレビュー」欄があり、入力しながら自動でPDFの
     見た目が表示されます（少し待つと反映されます）。
     「請求書」「領収証」のどちらを見るかは、プレビュー欄の上にある
     ボタンで切り替えられます。うまく表示されないときは
     「🔄 今すぐ更新」ボタンを押してください。
     入力欄とプレビューの境目（仕切り）はドラッグで動かせます。
     元の配置に戻したいときは、画面右上の「↔ 画面の配置を元に戻す」
     ボタンを押すか、仕切りをダブルクリックしてください。

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


def _grid_table_header(parent, headers):
    """入力表の見出しを parent の0行目に並べる。見出しと入力欄を同じ grid に
    入れることで、文字の大きさが違っても列の位置が必ずそろうようにしている。
    headers は (見出し, 寄せ方) のリスト。寄せ方は "w"（左）か "e"（右）。"""
    for col, (text, sticky) in enumerate(headers):
        ttk.Label(parent, text=text, font=(UI_FONT_FAMILY, 10, "bold")).grid(
            row=0, column=col, padx=2, sticky=sticky,
        )


class ItemRow:
    """品目テーブルの1行分の入力欄をまとめたクラス。
    入力欄は見出しと同じ parent の grid に、1行ずつ下に追加していく。"""

    def __init__(self, parent, on_change, on_remove):
        self.on_change = on_change

        self.date_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.qty_var = tk.StringVar(value="1")
        self.price_var = tk.StringVar()
        self.tax_var = tk.StringVar()
        self.note_var = tk.StringVar()
        self.amount_var = tk.StringVar(value="￥0")

        widths = [10, 26, 6, 10, 10, 14]
        e1 = ttk.Entry(parent, textvariable=self.date_var, width=widths[0])
        e2 = ttk.Entry(parent, textvariable=self.name_var, width=widths[1])
        e3 = ttk.Entry(parent, textvariable=self.qty_var, width=widths[2])
        e4 = ttk.Entry(parent, textvariable=self.price_var, width=widths[3])
        lbl_amount = ttk.Label(parent, textvariable=self.amount_var, width=widths[4], anchor="e")
        e6 = ttk.Entry(parent, textvariable=self.tax_var, width=8)
        e7 = ttk.Entry(parent, textvariable=self.note_var, width=widths[5])
        btn_del = ttk.Button(parent, text="削除", width=5,
                              command=lambda: on_remove(self))

        # 途中の行を削除しても、新しい行は必ずいちばん下に追加される
        grid_row = parent.grid_size()[1]
        self.widgets = [e1, e2, e3, e4, lbl_amount, e6, e7, btn_del]
        for i, w in enumerate(self.widgets):
            w.grid(row=grid_row, column=i, padx=2, pady=2, sticky="w")

        for var in (self.qty_var, self.price_var):
            var.trace_add("write", lambda *_: self._recalc())

        ToolTip(e1, "請求する日付（例：9月1日）")
        ToolTip(e2, "請求する内容の名前（例：準組合費 令和8年9〜11月）")
        ToolTip(e3, "個数（数字のみ）")
        ToolTip(e4, "1個あたりの値段（数字のみ、円マーク不要）")
        ToolTip(e6, "消費税額。分からなければ空欄のままでOKです")
        ToolTip(e7, "備考・補足があれば入力（任意）")

    def destroy(self):
        for w in self.widgets:
            w.destroy()

    def dummy_vars(self):
        """DUMMY_ITEMS の並び（日付・品名・数量・単価・消費税・摘要）に対応する入力欄。"""
        return [self.date_var, self.name_var, self.qty_var, self.price_var, self.tax_var, self.note_var]

    def reset(self):
        """新しく行を追加したときと同じ、空の状態に戻す。"""
        for var in self.dummy_vars():
            var.set("")
        self.qty_var.set("1")

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
    """振込先テーブルの1行分。ItemRow と同じく、見出しと同じ grid に追加する。"""

    def __init__(self, parent, on_remove):
        self.name_var = tk.StringVar()
        self.branch_var = tk.StringVar()
        self.code_var = tk.StringVar()
        self.type_var = tk.StringVar(value="普通")
        self.number_var = tk.StringVar()

        widths = [16, 10, 6, 6, 12]
        entries = [
            ttk.Entry(parent, textvariable=self.name_var, width=widths[0]),
            ttk.Entry(parent, textvariable=self.branch_var, width=widths[1]),
            ttk.Entry(parent, textvariable=self.code_var, width=widths[2]),
            ttk.Entry(parent, textvariable=self.type_var, width=widths[3]),
            ttk.Entry(parent, textvariable=self.number_var, width=widths[4]),
        ]
        grid_row = parent.grid_size()[1]
        for i, w in enumerate(entries):
            w.grid(row=grid_row, column=i, padx=2, pady=2, sticky="w")
        btn = ttk.Button(parent, text="削除", width=5, command=lambda: on_remove(self))
        btn.grid(row=grid_row, column=len(entries), padx=2)
        self.widgets = entries + [btn]

        ToolTip(entries[0], "金融機関名（例：〇〇信用金庫）")
        ToolTip(entries[1], "支店名（例：千駄ヶ谷支店）")
        ToolTip(entries[2], "支店番号（分かれば入力、なくてもOK）")
        ToolTip(entries[3], "口座種類（普通 または 当座）")
        ToolTip(entries[4], "口座番号")

    def destroy(self):
        for w in self.widgets:
            w.destroy()

    def dummy_vars(self):
        """DUMMY_BANKS の並び（金融機関名・支店名・店番・口座種類・口座番号）に対応する入力欄。"""
        return [self.name_var, self.branch_var, self.code_var, self.type_var, self.number_var]

    def reset(self):
        """新しく行を追加したときと同じ、空の状態に戻す。"""
        for var in self.dummy_vars():
            var.set("")
        self.type_var.set("普通")

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
        # ダミーデータを入れたら、その起動中は設定・取引先履歴を保存しない
        # （本番の設定に「ダミー株式会社」などが混ざらないようにするため）
        self._dummy_active = False
        # ダミーで入れた場所の記録（もう一度ボタンを押したときに、そこだけ空欄に戻すため）
        self._dummy_filled = None
        root.title(f"請求書かんたん作成ツール - {APP_VERSION}")
        # 右側にPDFプレビューを表示するため、画面サイズはフルHD固定にしている。
        root.geometry("1920x1080")

        self._build_layout()
        self._load_defaults_into_form()
        # ウィンドウの大きさが決まってから、左右の分割を既定の比率にする
        self.root.after(200, self._reset_pane_layout)

    # ---------------------------------------------------------- UI 構築
    def _build_layout(self):
        big_font = (UI_FONT_FAMILY, 11)
        header_font = (UI_FONT_FAMILY, 14, "bold")
        self.root.option_add("*Font", big_font)

        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="請求書かんたん作成ツール", font=(UI_FONT_FAMILY, 18, "bold")).pack(side="left")

        # PDFの書式は請求書・領収証のどちらにも効くので、いちばん上で選ぶ。
        # 選んだ書式は設定ファイルに保存され、次回起動時も同じ書式になる。
        format_frame = ttk.Frame(top)
        format_frame.pack(side="left", padx=(30, 0))
        ttk.Label(format_frame, text="PDFの書式：", font=(UI_FONT_FAMILY, 12, "bold")).pack(side="left")
        saved_format = self.cfg.get("doc_format", "standard")
        if saved_format not in DOC_FORMAT_LABELS:
            saved_format = "standard"
        self.doc_format_var = tk.StringVar(value=saved_format)
        self.doc_format_combo = ttk.Combobox(
            format_frame, values=list(DOC_FORMAT_LABELS.values()), state="readonly",
            width=24, font=(UI_FONT_FAMILY, 12),
        )
        self.doc_format_combo.set(DOC_FORMAT_LABELS[saved_format])
        self.doc_format_combo.pack(side="left")
        self.doc_format_combo.bind("<<ComboboxSelected>>", self._on_doc_format_changed)
        ToolTip(
            format_frame,
            "「クラシック」は、これまで使っていたシステムの請求書・領収書と\n"
            "同じ配置で作成します（宛先は名前と「御中」のみ、但し書きは印字されません）。\n"
            "選んだ書式は次回からも自動的に使われます。",
        )

        ttk.Button(top, text="？ 使い方ヘルプ", command=self.show_help).pack(side="right")
        ttk.Button(top, text="🔄 アップデート確認", command=self.check_for_updates).pack(side="right", padx=(0, 8))
        ttk.Button(
            top, text="↔ 画面の配置を元に戻す", command=self._reset_pane_layout,
        ).pack(side="right", padx=(0, 8))

        # 画面を左右2カラムに分割：左＝入力フォーム、右＝PDFプレビュー。
        # ttk.PanedWindow は仕切り線が細くて掴みにくいため、仕切りの幅を指定できる
        # tk.PanedWindow を使っている。仕切りをダブルクリックしても元の配置に戻る。
        self.main_paned = main_paned = tk.PanedWindow(
            self.root, orient="horizontal", sashwidth=10, sashrelief="raised",
            sashcursor="sb_h_double_arrow", opaqueresize=True, bd=0,
        )
        main_paned.pack(fill="both", expand=True)
        main_paned.bind("<Double-Button-1>", self._reset_pane_layout)

        left_pane = ttk.Frame(main_paned)
        main_paned.add(left_pane, minsize=400, stretch="always")
        right_pane = ttk.Frame(main_paned)
        main_paned.add(right_pane, minsize=300, stretch="always")

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
        # 日本語の変換中の文字を、入力欄と同じフォントで表示させる（Windowsのみ）
        self.root.bind_all("<FocusIn>", _match_ime_font_to_widget, add="+")

        body = self.body

        # ---- 出力テスト用：ダミーデータ ----
        dummy_row = ttk.Frame(body)
        dummy_row.pack(fill="x", pady=(0, 4))
        # 1回目で入力、もう一度押すとダミーで入れた欄だけを空欄に戻す（切り替え式）
        self.dummy_button = ttk.Button(dummy_row, text=DUMMY_BUTTON_FILL, command=self.toggle_dummy_data)
        self.dummy_button.pack(side="left")
        self.dummy_status_var = tk.StringVar(value=DUMMY_STATUS_IDLE)
        self.dummy_status_label = ttk.Label(dummy_row, textvariable=self.dummy_status_var, foreground="#666")
        self.dummy_status_label.pack(side="left", padx=10)

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
            sec1, "請求書番号", width=20, hint="※ 任意。領収証にも同じ番号が印字されます",
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
        self.dest_fax = self._labeled_entry(sec2, "FAX番号", width=20, hint="※ なければ空欄")

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
        self.issuer_fax = self._labeled_entry(sec3, "FAX番号", width=20, hint="※ なければ空欄")

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

        self.items_frame = ttk.Frame(sec4)
        self.items_frame.pack(anchor="w", fill="x")
        _grid_table_header(self.items_frame, [
            ("日付", "w"), ("品名", "w"), ("数量", "w"), ("単価", "w"),
            ("金額(自動)", "e"), ("消費税", "w"), ("摘要", "w"),
        ])
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
        self.bank_holder1 = self._labeled_entry(sec6, "名義人", width=50, hint="例：〇〇 代表者名")
        self.bank_holder2 = self._labeled_entry(sec6, "住所・電話など", width=50, hint="※ 任意")

        self.banks_frame = ttk.Frame(sec6)
        self.banks_frame.pack(anchor="w", fill="x", pady=(6, 0))
        _grid_table_header(self.banks_frame, [
            ("金融機関名", "w"), ("支店名", "w"), ("店番", "w"), ("口座種類", "w"), ("口座番号", "w"),
        ])
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
        bottom.columnconfigure(2, weight=1)

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
        receipt_col.grid(row=0, column=1, sticky="nsew", padx=(6, 6))
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

        both_col = ttk.Frame(bottom)
        both_col.grid(row=0, column=2, sticky="nsew", padx=(12, 0))
        both_btn = tk.Button(
            both_col, text="📑 請求書・領収証を一括作成", font=(UI_FONT_FAMILY, 14, "bold"),
            bg="#5b4bb7", fg="white", activebackground="#463894", activeforeground="white",
            height=2, command=self.on_create_both,
        )
        both_btn.pack(fill="x")
        ttk.Label(
            both_col,
            text="保存するフォルダを1回選ぶだけで、請求書PDFと領収証PDFの両方をまとめて作成します。",
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
                data = self._collect_receipt_data(self._receipt_date())
                build_fn = self._receipt_builder()
            else:
                data = self._collect_invoice_data(self._issue_date())
                build_fn = self._invoice_builder()

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

    # ---------------------------------------------------------- 書式の切り替え
    def _on_doc_format_changed(self, _event=None):
        label = self.doc_format_combo.get()
        key = next((k for k, v in DOC_FORMAT_LABELS.items() if v == label), "standard")
        self.doc_format_var.set(key)
        self.doc_format_combo.selection_clear()  # 選んだ文字が反転表示のまま残らないようにする
        self.cfg["doc_format"] = key
        save_config(self.cfg)
        self._schedule_preview_update()

    # ---------------------------------------------------------- 画面の左右分割
    def _reset_pane_layout(self, _event=None):
        """左（入力欄）と右（プレビュー）の幅を、既定の 3：2 に戻す。"""
        self.root.update_idletasks()
        width = self.main_paned.winfo_width()
        if width > 1:
            self.main_paned.sash_place(0, int(width * 0.6), 0)
        return "break"

    def _invoice_builder(self):
        from pdf_builder import build_invoice_pdf, build_invoice_pdf_classic
        return build_invoice_pdf_classic if self.doc_format_var.get() == "classic" else build_invoice_pdf

    def _receipt_builder(self):
        from pdf_builder import build_receipt_pdf, build_receipt_pdf_classic
        return build_receipt_pdf_classic if self.doc_format_var.get() == "classic" else build_receipt_pdf

    def _section(self, parent, title, help_text):
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.pack(fill="x", pady=8)
        if help_text:
            ttk.Label(frame, text=help_text, foreground="#666", wraplength=880).pack(anchor="w", pady=(0, 6))
        return frame

    def _labeled_entry(self, parent, label, width=30, hint=""):
        """見出し＋入力欄の1行を作る。見出しは幅を揃えるため短くし、
        「任意」などの補足は hint として入力欄の右に灰色で表示する。"""
        row = ttk.Frame(parent)
        row.pack(anchor="w", pady=2, fill="x")
        ttk.Label(row, text=label, width=22, anchor="w").pack(side="left")
        var = tk.StringVar()
        ttk.Entry(row, textvariable=var, width=width).pack(side="left")
        if hint:
            ttk.Label(row, text=hint, foreground="#666").pack(side="left", padx=10)
        return var

    # ---------------------------------------------------------- 行操作
    def add_item_row(self):
        row = ItemRow(self.items_frame, self.recalc_total, self.remove_item_row)
        self.item_rows.append(row)
        self._schedule_preview_update()

    def remove_item_row(self, row):
        if len(self.item_rows) <= 1:
            messagebox.showinfo("お知らせ", "最低1行は必要です。")
            return
        row.destroy()
        self.item_rows.remove(row)
        self.recalc_total()
        self._schedule_preview_update()

    def add_bank_row(self):
        row = BankRow(self.banks_frame, self.remove_bank_row)
        self.bank_rows.append(row)
        self._schedule_preview_update()

    def remove_bank_row(self, row):
        if len(self.bank_rows) <= 1:
            messagebox.showinfo("お知らせ", "最低1行は必要です。")
            return
        row.destroy()
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
        self.issuer_fax.set(cfg.get("issuer_fax", ""))
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
                r.destroy()
            self.bank_rows.clear()
            for b in banks:
                if not any(b.values()):
                    continue
                row = BankRow(self.banks_frame, self.remove_bank_row)
                row.name_var.set(b.get("name", ""))
                row.branch_var.set(b.get("branch", ""))
                row.code_var.set(b.get("code", ""))
                row.type_var.set(b.get("type", "普通"))
                row.number_var.set(b.get("number", ""))
                self.bank_rows.append(row)

        self._schedule_preview_update()

    def _save_current_settings(self):
        if self._dummy_active:
            return  # ダミーデータ使用中は、本番の設定・取引先履歴を上書きしない
        self.cfg["issuer_zip"] = self.issuer_zip.get().strip()
        self.cfg["issuer_address"] = self.issuer_address.get().strip()
        self.cfg["issuer_name"] = self.issuer_name.get().strip()
        self.cfg["issuer_representative"] = self.issuer_representative.get().strip()
        self.cfg["issuer_tel"] = self.issuer_tel.get().strip()
        self.cfg["issuer_fax"] = self.issuer_fax.get().strip()
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

    # ---------------------------------------------------------- ダミーデータ（出力テスト用）
    def toggle_dummy_data(self):
        if self._dummy_filled is None:
            self.fill_dummy_data()
        else:
            self.clear_dummy_data()

    def fill_dummy_data(self):
        """空いている欄だけにダミーデータを入れる（入力済みの欄はそのまま）。
        会社印が未設定なら、1:1の「見本之印」の画像を作って使う。
        入れた場所は self._dummy_filled に記録し、clear_dummy_data で元に戻せるようにする。"""
        filled = {"fields": [], "remarks": False, "items": [], "added_items": [],
                  "banks": [], "added_banks": [], "seal": False}
        for key, value in DUMMY_FIELDS.items():
            var = getattr(self, key)
            if not var.get().strip():
                var.set(value)
                filled["fields"].append((var, value))
        if not self.remarks_text.get("1.0", "end").strip():
            self.remarks_text.insert("1.0", DUMMY_REMARKS)
            filled["remarks"] = True

        # 品目・振込先は、表がまるごと空のときだけ入れる（途中の行に混ぜない）
        if all(r.is_blank() for r in self.item_rows):
            while len(self.item_rows) < len(DUMMY_ITEMS):
                self.add_item_row()
                filled["added_items"].append(self.item_rows[-1])
            for row, values in zip(self.item_rows, DUMMY_ITEMS):
                for var, value in zip(row.dummy_vars(), values):
                    var.set(value)
                filled["items"].append((row, values))
            self.recalc_total()
        if all(r.is_blank() for r in self.bank_rows):
            while len(self.bank_rows) < len(DUMMY_BANKS):
                self.add_bank_row()
                filled["added_banks"].append(self.bank_rows[-1])
            for row, values in zip(self.bank_rows, DUMMY_BANKS):
                for var, value in zip(row.dummy_vars(), values):
                    var.set(value)
                filled["banks"].append((row, values))

        if not self.cfg.get("seal_image_path"):
            try:
                from pdf_builder import build_dummy_seal_png
                build_dummy_seal_png(DUMMY_SEAL_PATH)
                self.seal_path_label.config(text="（ダミーの会社印「見本之印」を使用中）")
                filled["seal"] = True
            except Exception:
                pass  # 印影が作れなくても、ほかのダミーデータでの出力テストはできる

        self._dummy_filled = filled
        self._dummy_active = True
        self.dummy_button.config(text=DUMMY_BUTTON_CLEAR)
        self.dummy_status_var.set(DUMMY_STATUS_ACTIVE)
        self.dummy_status_label.config(foreground="#b00020")
        self._schedule_preview_update()

    def clear_dummy_data(self):
        """fill_dummy_data で入れた欄を空欄に戻す。ダミーを入れたあとに
        書き換えた欄は、本物の内容かもしれないので消さずに残す。"""
        filled = self._dummy_filled
        for var, value in filled["fields"]:
            if var.get() == value:
                var.set("")
        if filled["remarks"] and self.remarks_text.get("1.0", "end").strip() == DUMMY_REMARKS:
            self.remarks_text.delete("1.0", "end")

        for rows, entries, added, remove in (
            (self.item_rows, filled["items"], filled["added_items"], self.remove_item_row),
            (self.bank_rows, filled["banks"], filled["added_banks"], self.remove_bank_row),
        ):
            for row, values in entries:
                if row in rows and tuple(v.get() for v in row.dummy_vars()) == tuple(values):
                    row.reset()
            # ダミーのために増やした行は、空のままなら取り除く
            for row in added:
                if row in rows and row.is_blank() and len(rows) > 1:
                    remove(row)
        self.recalc_total()

        if filled["seal"]:
            self.seal_path_label.config(text="（未設定）")

        self._dummy_filled = None
        self._dummy_active = False
        self.dummy_button.config(text=DUMMY_BUTTON_FILL)
        self.dummy_status_var.set(DUMMY_STATUS_IDLE)
        self.dummy_status_label.config(foreground="#666")
        self._schedule_preview_update()

    def _current_seal_path(self):
        """PDFに使う印影画像。会社印が未設定で、ダミーデータ使用中ならダミーの印影を使う。"""
        seal = self.cfg.get("seal_image_path", "")
        if not seal and self._dummy_active and os.path.exists(DUMMY_SEAL_PATH):
            return DUMMY_SEAL_PATH
        return seal

    # ---------------------------------------------------------- 日付
    def _issue_date(self):
        y, m, d = int(self.date_year.get()), int(self.date_month.get()), int(self.date_day.get())
        return datetime.date(y, m, d)

    def _receipt_date(self):
        if self.receipt_same_date_var.get():
            return self._issue_date()
        y, m, d = int(self.receipt_year.get()), int(self.receipt_month.get()), int(self.receipt_day.get())
        return datetime.date(y, m, d)

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
            "issuer_fax": self.issuer_fax.get().strip(),
            "show_issuer_block": bool(self.show_issuer_var.get()),
            "show_note_column": bool(self.show_note_column_var.get()),
            "seal_path": self._current_seal_path(),
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
            "issuer_fax": self.issuer_fax.get().strip(),
            "show_issuer_block": bool(self.show_issuer_var.get()),
            "seal_path": self._current_seal_path(),
        }

    # ---------------------------------------------------------- PDF作成
    def on_create_pdf(self):
        errors = self._validate()
        if errors:
            messagebox.showwarning("入力内容を確認してください", "\n\n".join(errors))
            return

        self._save_current_settings()

        issue_date = self._issue_date()
        data = self._collect_invoice_data(issue_date)

        default_name = f"請求書_{issue_date.strftime('%Y%m%d')}_{data['dest_name'] or '宛先未設定'}.pdf"
        save_path = self._pick_save_path("請求書PDFの保存先を選んでください", default_name)
        if not save_path:
            return

        try:
            self._invoice_builder()(save_path, data)
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

        receipt_date = self._receipt_date()
        data = self._collect_receipt_data(receipt_date)

        default_name = f"領収証_{receipt_date.strftime('%Y%m%d')}_{data['dest_name'] or '宛先未設定'}.pdf"
        save_path = self._pick_save_path("領収証PDFの保存先を選んでください", default_name)
        if not save_path:
            return

        try:
            self._receipt_builder()(save_path, data)
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

    # ---------------------------------------------------------- 請求書・領収証の一括作成
    def on_create_both(self):
        # 請求書・領収証の両方の入力チェックをまとめて表示する（同じ指摘は1回だけ）
        errors = list(dict.fromkeys(self._validate() + self._validate_receipt()))
        if errors:
            messagebox.showwarning("入力内容を確認してください", "\n\n".join(errors))
            return

        self._save_current_settings()

        issue_date = self._issue_date()
        receipt_date = self._receipt_date()
        invoice_data = self._collect_invoice_data(issue_date)
        receipt_data = self._collect_receipt_data(receipt_date)
        dest = invoice_data["dest_name"] or "宛先未設定"

        folder = filedialog.askdirectory(
            title="請求書・領収証PDFを保存するフォルダを選んでください",
            initialdir=self._default_save_dir(),
        )
        if not folder:
            return

        jobs = [
            ("請求書", os.path.join(folder, _safe_filename(f"請求書_{issue_date.strftime('%Y%m%d')}_{dest}.pdf")),
             self._invoice_builder(), invoice_data),
            ("領収証", os.path.join(folder, _safe_filename(f"領収証_{receipt_date.strftime('%Y%m%d')}_{dest}.pdf")),
             self._receipt_builder(), receipt_data),
        ]
        existing = [os.path.basename(path) for _, path, _, _ in jobs if os.path.exists(path)]
        if existing and not messagebox.askyesno(
            "上書きの確認",
            "同じ名前のファイルがすでにあります。上書きしますか？\n\n" + "\n".join(existing),
        ):
            return

        for label, path, build_fn, data in jobs:
            try:
                build_fn(path, data)
            except Exception:
                err = traceback.format_exc()
                messagebox.showerror(
                    "PDFの作成に失敗しました",
                    f"申し訳ありません、{label}PDFの作成中に問題が発生しました。\n"
                    "入力内容をもう一度ご確認のうえ、お試しください。\n\n"
                    "（技術情報）\n" + err[-800:],
                )
                return

        self.cfg["last_save_dir"] = folder
        save_config(self.cfg)

        paths = "\n".join(path for _, path, _, _ in jobs)
        if messagebox.askyesno(
            "完成しました",
            f"請求書PDFと領収証PDFを作成しました。\n\n{paths}\n\n保存したフォルダを開きますか？",
        ):
            self._open_path(folder)

    # ---------------------------------------------------------- 保存・オープン共通処理
    def _default_save_dir(self):
        default_dir = self.cfg.get("last_save_dir") or os.path.expanduser("~/Desktop")
        if not os.path.isdir(default_dir):
            default_dir = os.path.expanduser("~")
        return default_dir

    def _pick_save_path(self, title, default_name):
        return filedialog.asksaveasfilename(
            title=title,
            initialdir=self._default_save_dir(),
            initialfile=_safe_filename(default_name),
            defaultextension=".pdf",
            filetypes=[("PDFファイル", "*.pdf")],
        )

    def _open_path(self, path):
        """ファイルやフォルダを、OS標準のアプリで開く。"""
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception:
            messagebox.showinfo("お知らせ", "ファイルは作成されましたが、自動で開けませんでした。\n保存先フォルダから開いてください。")

    def _offer_open_file(self, save_path, doc_label):
        if messagebox.askyesno("完成しました", f"{doc_label}PDFを作成しました。\n\n{save_path}\n\nこのファイルを開きますか？"):
            self._open_path(save_path)


def _safe_filename(name):
    """ファイル名に使えない文字を取り除く。"""
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "")
    return name


def main():
    _ensure_bundled_font_on_linux()
    _setup_linux_input_method()
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
