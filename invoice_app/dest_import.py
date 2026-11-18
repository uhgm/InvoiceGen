# -*- coding: utf-8 -*-
"""
取引先（宛先）の一覧を、テキスト・CSV・Excel ファイルから読み込む。

対応する形式：
  - .csv  … カンマ区切り（Excel で「CSV」として保存したもの。Shift_JIS / UTF-8 どちらも可）
  - .txt  … 1行に1社の名前だけ、またはタブ／カンマ区切り
            （Excel の「テキスト（タブ区切り）」「Unicode テキスト」も可）
  - .xlsx / .xlsm … Excel ブック（開いたときに表示されるシートを読む）

★なぜ Excel を標準ライブラリだけで読むのか★
アプリ内の「アップデート確認」はファイルを上書きするだけで pip を動かさない。
openpyxl などの部品を新しく必要にすると、更新しただけのPCでは Excel の
取り込みが動かなくなる。.xlsx の中身は「ZIP に入った XML」なので、
値を読むだけなら zipfile と ElementTree で十分足りる。
（古い .xls 形式は中身がまったく別物なので対応しない。.xlsx か CSV で保存し直してもらう）

見出し行（「会社名」「住所」など）があれば、その列名で項目を判断する。
見出しがなければ、左の列から順に 会社名・郵便番号・住所・電話番号・FAX番号 として読む。

このファイルは PySide6 を使わない（画面なしで動作確認できるように）。
"""
import csv
import io
import os
import posixpath
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

FIELDS = ("name", "zip", "addr", "tel", "fax")
FIELD_LABELS = {
    "name": "会社名・団体名",
    "zip": "郵便番号",
    "addr": "住所",
    "tel": "電話番号",
    "fax": "FAX番号",
}

# 見出しの文字にこれらの言葉が含まれていれば、その項目の列とみなす。
# 上から順に調べる（「FAX番号」を電話番号と取り違えない、「取引先住所」を
# 会社名と取り違えない、などのため、名前は最後に調べる）。
_HEADER_KEYWORDS = (
    ("fax", ("fax", "ファックス", "ファクス", "ﾌｧｯｸｽ")),
    ("tel", ("電話", "tel", "phone", "携帯")),
    ("zip", ("郵便", "〒", "zip", "postal", "postcode")),
    ("addr", ("住所", "所在地", "address")),
    ("name", ("会社", "団体", "取引先", "宛先", "宛名", "名称", "社名", "顧客", "得意先",
              "相手先", "請求先", "氏名", "名前", "name", "company")),
)

# 見出し行を探すのは、最初のこの行数まで（表のタイトル行などが上にあっても見つけられるように）
_HEADER_SEARCH_ROWS = 10

SUPPORTED_EXTS = (".csv", ".txt", ".tsv", ".xlsx", ".xlsm")
FILE_DIALOG_FILTER = (
    "取引先の一覧ファイル (*.csv *.txt *.tsv *.xlsx *.xlsm);;"
    "Excel ブック (*.xlsx *.xlsm);;CSV ファイル (*.csv);;テキスト ファイル (*.txt *.tsv);;"
    "すべてのファイル (*)"
)


class ImportError_(Exception):
    """読み込めなかった理由を、そのまま画面に出せる日本語で持つ例外。"""


class ImportResult:
    def __init__(self, entries, has_header, columns, skipped_rows, duplicate_rows, sheet_name=""):
        self.entries = entries              # [{"name","zip","addr","tel","fax"}, ...]（ファイルの順）
        self.has_header = has_header        # 見出し行で項目を判断したか
        self.columns = columns              # 読み取った項目 → 列見出し（見出しなしなら列番号の説明）
        self.skipped_rows = skipped_rows    # 会社名が空で飛ばした行の数
        self.duplicate_rows = duplicate_rows  # ファイル内で同じ会社名が重なった行の数（後の行で上書き）
        self.sheet_name = sheet_name        # Excel のとき、読んだシートの名前


# ------------------------------------------------------------------
# ファイル → 表（行のリスト）
# ------------------------------------------------------------------
def _decode_text(raw):
    """文字コードを判定して文字列にする。BOM付きUTF-16（Excelの「Unicodeテキスト」）、
    UTF-8、Shift_JIS（日本語版Excelの普通のCSV）の順に試す。"""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ImportError_(
        "ファイルの文字コードを判別できませんでした。\n"
        "Excel などで「CSV UTF-8」または「CSV（コンマ区切り）」として保存し直してから、もう一度お試しください。"
    )


def _read_text_rows(path):
    with open(path, "rb") as f:
        raw = f.read()
    text = _decode_text(raw)
    if "\x00" in text:
        raise ImportError_("文字のファイルではないようです。CSV・テキスト・Excel（.xlsx）のファイルを選んでください。")
    delimiter = "\t" if "\t" in text else ","
    return [list(row) for row in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)]


def _local(tag):
    """XML のタグ名から名前空間を取り除く（通常の .xlsx と Strict 形式の両方に対応するため）。"""
    return tag.rsplit("}", 1)[-1]


def _children(elem, name):
    return [c for c in elem if _local(c.tag) == name]


def _attr(elem, name):
    """名前空間付きの属性（r:id など）も、ローカル名で取り出す。"""
    for key, value in elem.attrib.items():
        if _local(key) == name:
            return value
    return None


def _text_of(elem):
    """セルの文字列。ふりがな（<rPh>）の中の文字は含めない。"""
    parts = []

    def _walk(e):
        name = _local(e.tag)
        if name == "rPh":
            return
        if name == "t" and e.text:
            parts.append(e.text)
        for c in e:
            _walk(c)

    _walk(elem)
    return "".join(parts)


def _col_index(ref):
    """セル番地（例：'C12'）の列を 0 始まりの番号にする。"""
    m = re.match(r"([A-Za-z]+)", ref or "")
    if not m:
        return None
    n = 0
    for ch in m.group(1).upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _format_number(value):
    """数値セルの値を文字にする（1000001.0 → '1000001'）。"""
    try:
        num = float(value)
    except ValueError:
        return value
    if num.is_integer():
        return str(int(num))
    return value


def _resolve_target(target):
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("xl", target))


def _read_xlsx_rows(path):
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ImportError_(
            "Excel ファイルとして開けませんでした。\n"
            "ファイルが壊れていないか、パスワードが設定されていないかご確認ください。"
        )
    with zf:
        names = set(zf.namelist())
        try:
            workbook = ET.fromstring(zf.read("xl/workbook.xml"))
            rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        except KeyError:
            raise ImportError_("Excel ファイルの中身を読み取れませんでした。")

        # 開いたときに表示されるシート（なければ最初のシート）を読む
        sheets = [s for e in workbook if _local(e.tag) == "sheets" for s in _children(e, "sheet")]
        if not sheets:
            raise ImportError_("Excel ファイルにシートが見つかりませんでした。")
        active = 0
        for views in _children(workbook, "bookViews"):
            for view in _children(views, "workbookView"):
                try:
                    active = int(view.get("activeTab", "0"))
                except ValueError:
                    pass
        sheet = sheets[active] if 0 <= active < len(sheets) else sheets[0]
        rel_id = _attr(sheet, "id")
        sheet_path = None
        for rel in rels:
            if rel.get("Id") == rel_id:
                sheet_path = _resolve_target(rel.get("Target", ""))
        if not sheet_path or sheet_path not in names:
            raise ImportError_("Excel ファイルのシートを読み取れませんでした。")

        shared = []
        if "xl/sharedStrings.xml" in names:
            sst = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            shared = [_text_of(si) for si in _children(sst, "si")]

        root = ET.fromstring(zf.read(sheet_path))

    rows = []
    for data in _children(root, "sheetData"):
        for row in _children(data, "row"):
            cells = {}
            next_col = 0
            for c in _children(row, "c"):
                col = _col_index(c.get("r"))
                if col is None:
                    col = next_col
                next_col = col + 1
                ctype = c.get("t", "n")
                v = next(iter(_children(c, "v")), None)
                raw = v.text if v is not None and v.text is not None else ""
                if ctype == "s":
                    try:
                        value = shared[int(raw)]
                    except (ValueError, IndexError):
                        value = ""
                elif ctype == "inlineStr":
                    value = "".join(_text_of(i) for i in _children(c, "is"))
                elif ctype in ("str", "e"):
                    value = raw if ctype == "str" else ""
                elif ctype == "b":
                    value = "TRUE" if raw == "1" else "FALSE"
                else:
                    value = _format_number(raw) if raw else ""
                cells[col] = value
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            else:
                rows.append([])
    return rows, sheet.get("name", "")


def read_rows(path):
    """ファイルを読み、(行のリスト, シート名) を返す。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xls":
        raise ImportError_(
            "古い形式の Excel ファイル（.xls）には対応していません。\n"
            "Excel でファイルを開き、「名前を付けて保存」で「Excel ブック（.xlsx）」"
            "または「CSV」を選んで保存し直してから、もう一度お試しください。"
        )
    try:
        if ext in (".xlsx", ".xlsm"):
            return _read_xlsx_rows(path)
        if zipfile.is_zipfile(path):
            # 拡張子が違っていても、中身が Excel ブックならそのまま読む
            return _read_xlsx_rows(path)
        return _read_text_rows(path), ""
    except ImportError_:
        raise
    except PermissionError:
        raise ImportError_("ファイルを開けませんでした。Excel などで開いたままになっていたら、閉じてからお試しください。")
    except OSError as e:
        raise ImportError_(f"ファイルを開けませんでした。\n（{e}）")
    except (ET.ParseError, csv.Error, ValueError) as e:
        raise ImportError_(f"ファイルの内容を読み取れませんでした。\n（{e}）")


# ------------------------------------------------------------------
# 表 → 取引先のリスト
# ------------------------------------------------------------------
def _norm_header(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or ""))).lower()


def _header_field(text):
    h = _norm_header(text)
    if not h:
        return None
    for field, keywords in _HEADER_KEYWORDS:
        if any(k in h for k in keywords):
            return field
    return None


def _find_header(rows):
    """見出し行を探す。見つかれば (行番号, {項目: [列番号...]}) 、なければ (None, None)。"""
    checked = 0
    for i, row in enumerate(rows):
        if not any(str(c).strip() for c in row):
            continue
        checked += 1
        if checked > _HEADER_SEARCH_ROWS:
            break
        mapping = {}
        for col, cell in enumerate(row):
            field = _header_field(cell)
            if field:
                mapping.setdefault(field, []).append(col)
        # 会社名の列があり、ほかにも見出しらしい列がある（または、その列の文字が見出しそのもの）
        if "name" in mapping and (len(mapping) >= 2 or _is_pure_name_header(row, mapping["name"][0])):
            return i, mapping
    return None, None


# 見出しが会社名の列1つだけのとき（1行に1社だけの一覧）に、見出しとみなす言葉。
# 「テスト会社」のような実際の社名を見出しと取り違えないよう、完全に一致するものだけにする。
_NAME_ONLY_HEADERS = {
    "会社", "会社名", "団体名", "会社名・団体名", "会社名/団体名", "会社・団体名", "取引先", "取引先名",
    "宛先", "宛先名", "宛名", "名称", "社名", "顧客", "顧客名", "得意先", "得意先名", "相手先",
    "請求先", "請求先名", "氏名", "名前", "name", "company", "companyname",
}


def _is_pure_name_header(row, col):
    """「会社名」「取引先名」のような見出しの言葉そのものか（実際の社名と区別する）。"""
    return _norm_header(row[col]) in _NAME_ONLY_HEADERS


def _clean(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    # NFKC で全角スペースも半角になるので、連続する空白を1つにまとめる
    return re.sub(r"\s+", " ", text)


def _clean_name(value):
    """会社名。「御中」は PDF に自動で印字されるので、末尾に付いていたら取り除く。
    名前は入力されたとおりの文字（全角・半角）を残す。"""
    name = str(value or "").strip()
    name = re.sub(r"[\s　]*御中$", "", name).strip()
    return name


def _clean_zip(value):
    text = _clean(value).lstrip("〒").strip()
    digits = re.sub(r"\D", "", text)
    if re.fullmatch(r"\d{6,7}", text):
        # Excel の数値セルで先頭の 0 が消えた郵便番号（例：0600001 → 600001）も直す
        digits = digits.zfill(7)
        return f"{digits[:3]}-{digits[3:]}"
    return text


def _cell(row, col):
    return row[col] if col < len(row) else ""


def parse_rows(rows, sheet_name=""):
    header_row, mapping = _find_header(rows)
    if header_row is None:
        has_header = False
        mapping = {field: [i] for i, field in enumerate(FIELDS)}
        data_rows = rows
        columns = {field: f"左から{i + 1}列目" for i, field in enumerate(FIELDS)}
    else:
        has_header = True
        data_rows = rows[header_row + 1:]
        head = rows[header_row]
        columns = {field: "＋".join(str(head[c]).strip() for c in cols) for field, cols in mapping.items()}

    entries = {}
    order = []
    skipped = 0
    duplicates = 0
    for row in data_rows:
        if not any(str(c).strip() for c in row):
            continue  # 空の行は数えない
        entry = {}
        for field in FIELDS:
            cols = mapping.get(field, [])
            if field == "name":
                entry[field] = _clean_name(_cell(row, cols[0])) if cols else ""
            elif field == "addr":
                # 「住所1」「住所2」のように分かれていれば、つなげて1つにする
                entry[field] = " ".join(v for v in (_clean(_cell(row, c)) for c in cols) if v)
            elif field == "zip":
                entry[field] = _clean_zip(_cell(row, cols[0])) if cols else ""
            else:
                entry[field] = _clean(_cell(row, cols[0])) if cols else ""
        if not entry["name"]:
            skipped += 1
            continue
        prev = entries.get(entry["name"])
        if prev is not None:
            # 同じ会社名が2回出てきたら、後の行で入っている項目だけを書き換える
            duplicates += 1
            entry = {f: entry[f] or prev[f] for f in FIELDS}
        else:
            order.append(entry["name"])
        entries[entry["name"]] = entry

    return ImportResult([entries[n] for n in order], has_header, columns, skipped, duplicates, sheet_name)


def load_destinations(path):
    """ファイルから取引先を読み込む。読めなければ ImportError_（日本語の理由付き）を出す。"""
    rows, sheet_name = read_rows(path)
    result = parse_rows(rows, sheet_name)
    if not result.entries:
        raise ImportError_(
            "ファイルの中に、取り込める取引先が見つかりませんでした。\n"
            "1行目に「会社名」「住所」などの見出しを入れるか、"
            "いちばん左の列に会社名を入れてから、もう一度お試しください。"
        )
    return result


# ------------------------------------------------------------------
# 取り込んだ内容と、これまでの履歴を合わせる
# ------------------------------------------------------------------
STATUS_NEW = "new"
STATUS_UPDATE = "update"
STATUS_SAME = "same"
STATUS_LABELS = {STATUS_NEW: "新しく追加", STATUS_UPDATE: "内容を更新", STATUS_SAME: "登録済み（変更なし）"}


def merge_destinations(existing, imported):
    """取り込んだ取引先を履歴に合わせる。

    - 同じ名前がすでにあれば、ファイル側で空欄の項目は今の内容を残し、
      入っている項目だけを書き換える。
    - 取り込んだ取引先を（ファイルの順に）先頭に置き、残りの履歴をその後ろに続ける。

    (合わせた後のリスト, 取り込んだ各行の状態のリスト) を返す。"""
    by_name = {d.get("name"): d for d in existing}
    merged = []
    statuses = []
    for entry in imported:
        old = by_name.get(entry["name"])
        if old is None:
            new = {field: entry.get(field, "") for field in FIELDS}
            statuses.append(STATUS_NEW)
        else:
            new = {field: entry.get(field) or old.get(field, "") for field in FIELDS}
            same = all(new[f] == old.get(f, "") for f in FIELDS)
            statuses.append(STATUS_SAME if same else STATUS_UPDATE)
        merged.append(new)
    imported_names = {e["name"] for e in imported}
    merged.extend(d for d in existing if d.get("name") not in imported_names)
    return merged, statuses
