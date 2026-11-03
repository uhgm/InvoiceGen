# -*- coding: utf-8 -*-
"""
画面（main_window.py）と起動処理（invoice_generator.py）で共通に使う、
バージョン番号・保存場所・設定の読み書き・ダミーデータ・ヘルプ文など。

起動直後の「PySide6 が入っているかの確認」からも読み込まれるため、
このファイルは標準ライブラリだけで動くようにしている（PySide6 を import しない）。
"""
import datetime
import json
import os
import shutil
import sys
import unicodedata

APP_VERSION_NUM = "1.6"
APP_VERSION = f"Version {APP_VERSION_NUM}"
APP_CREDIT = "ClaudeCord & 井上"
APP_SUPPORT_EMAIL = "satoshi29333104@gmail.com"

# GitHubの「Releases」機能から、最新版の情報を自動取得するURL。
# 詳しい手順（Releaseの出し方）は updater.py の一番上のコメントに書いてあります。
UPDATE_MANIFEST_URL = "https://api.github.com/repos/uhgm/InvoiceGen/releases/latest"

# ------------------------------------------------------------------
# 起動フォルダ（この.pyファイル/ exe があるフォルダ）を基準にする
# ------------------------------------------------------------------
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_dir():
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


USER_DATA_DIR = _get_user_data_dir()
CONFIG_PATH = os.path.join(USER_DATA_DIR, "invoice_config.json")
_OLD_CONFIG_PATH = os.path.join(APP_DIR, "invoice_config.json")  # 旧バージョンの保存場所


def migrate_old_config_if_needed():
    """以前のバージョンで、アプリのフォルダに直接保存されていた設定を
    新しい保存場所（個人設定用フォルダ）に一度だけ引っ越す。"""
    try:
        if os.path.exists(_OLD_CONFIG_PATH) and not os.path.exists(CONFIG_PATH):
            shutil.copy2(_OLD_CONFIG_PATH, CONFIG_PATH)
            os.remove(_OLD_CONFIG_PATH)
    except Exception:
        pass  # 引っ越しに失敗しても、アプリの起動自体は続ける


# 設定の項目名は Tk 版（v1.5まで）と同じにしている。
# こうしておけば、更新しても振込先・取引先の履歴などがそのまま引き継がれる。
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
    "doc_format": "standard",  # PDFの書式。"standard"＝モダン、"classic"＝以前のシステムと同じ書式
    "destinations": [],  # 過去に入力した取引先（宛先）の履歴。新しい順。
}

MAX_DESTINATION_HISTORY = 50  # 取引先履歴の保存件数の上限

# PDFの書式（設定ファイルに保存する値 → 画面に出す名前）
DOC_FORMAT_LABELS = {
    "standard": "モダン",
    "classic": "クラシック",
}


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


# ------------------------------------------------------------------
# 出力テスト用のダミーデータ
# ------------------------------------------------------------------
# 「ダミーデータを下記の全空欄に入力」ボタンで入れる内容。
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
DUMMY_SEAL_PATH = os.path.join(USER_DATA_DIR, "dummy_seal.png")
DUMMY_BUTTON_FILL = "🧪 ダミーデータを下記の全空欄に入力"
DUMMY_BUTTON_CLEAR = "🧹 入力したダミーデータを消して空欄に戻す"
DUMMY_STATUS_IDLE = "出力テスト用です。空いている欄だけに入力します（入力済みの欄はそのまま）。"
DUMMY_STATUS_ACTIVE = (
    "ダミーデータ入力中：設定・取引先の履歴は保存されません。もう一度押すと消せます。"
)


# ------------------------------------------------------------------
# 小さな共通処理
# ------------------------------------------------------------------
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


def normalize_number(text) -> str:
    """数字の入力を、計算できる形（半角・カンマなし）にそろえる。
    日本語入力がオンのまま打った「１８００」や、「1,800円」「￥1,800」も受け付ける。"""
    text = unicodedata.normalize("NFKC", str(text or ""))
    for ch in (",", "円", "¥", "￥", " "):
        text = text.replace(ch, "")
    return text.strip()


def parse_number(text):
    """数字として読めれば float、空欄なら 0.0、読めなければ None を返す。"""
    text = normalize_number(text)
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


def safe_filename(name):
    """ファイル名に使えない文字を取り除く。"""
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "")
    return name


HELP_TEXT = """【使い方ガイド】

■ 全体の流れ
  ① 上から順番に、空いている欄を埋めていきます。
  ② 「品目」の表に、請求する内容（品名・数量・単価）を入力します。
     金額と合計金額は自動で計算されるので、電卓は不要です。
     数字は全角（１８００）でも、カンマ付き（1,800）でも大丈夫です。
  ③ 画面いちばん下の「📄 請求書PDFを作成」ボタンを押すと、保存する場所を
     聞かれるので、分かりやすい場所（例：デスクトップ）を選んで
     保存してください。

■ よくある質問
  Q. 何かの欄を間違えて入力してしまった
  A. その欄をクリックして、文字を消してから正しい内容を
     入力し直せば大丈夫です。何度でもやり直せます。

  Q. 発行日を変えたい
  A. 「① 発行日」の日付の右にある ▼ を押すと、カレンダーから選べます。
     PDFには自動で「令和◯年◯月◯日」の形で印字されます。

  Q. 品目の行が足りない／いらない行を消したい
  A. 表の下の「＋ 行を追加」ボタンで1行増えます。
     消したい行は、その行のいちばん右の「✕」を押してください。

  Q. 会社の印鑑（ハンコ）の画像はどこで設定するの？
  A. 「③ 請求元」の欄にある「印鑑画像を選ぶ」ボタンから、
     ハンコの画像ファイル（PNGなど）を選んでください。
     一度選ぶと、次回からは自動的に使われます。

  Q. 振込先の情報はどうなるの？
  A. 「⑥ 振込先」の欄に入力した内容が、次にこのアプリを開いたときも
     残るようになっています（毎回入力し直す必要はありません）。

  Q. 前に請求した取引先に、また請求書を出したい
  A. 「② 宛先」の「会社名・団体名」欄に、名前の一部を入力すると
     過去に入力した取引先の候補が下に出てきます。候補をクリックすると
     住所・電話番号なども自動で入力されます。
     一度PDFを作成した取引先は、自動的にこの候補に追加されます。
     間違えて登録してしまったときは「取引先の履歴を管理」ボタンから
     削除できます。

  Q. 領収証も発行したい
  A. 画面いちばん下の「🧾 領収証PDFを作成」ボタンを押すと、
     今入力している宛先・金額・発行元の情報をそのまま使って
     領収証PDFが作成されます。「⑦ 領収証」欄で、領収日（お金を
     受け取った日）や但し書きを変更できます（入力しなくても
     「お品代」として作成されます）。5万円以上の場合は、収入印紙欄が
     自動で印字されます（印紙そのものは含まれないので、あとで貼って
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
     ボタンで切り替えられます。
     入力欄とプレビューの境目（仕切り）はドラッグで動かせます。
     元の配置に戻したいときは、画面右上の「↔ 配置を元に戻す」
     ボタンを押すか、仕切りをダブルクリックしてください。

  Q. PDFはどこに保存されるの？
  A. PDFを作成するボタンを押したときに出てくる画面で、
     好きな保存場所とファイル名を選べます。

  Q. 操作を間違えて、アプリがおかしくなった
  A. 一度アプリを閉じて（右上の×ボタン）、もう一度
     ショートカットから開き直してください。入力していた内容は
     消えてしまいますが、故障ではありませんので安心してください。

分からないことがあれば、いつでもこの画面を開いて確認してください。
"""
