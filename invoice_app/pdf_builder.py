# -*- coding: utf-8 -*-
"""
請求書PDFの描画処理。
invoice_generator.py から呼び出される。
"""
import os
import sys
import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# 日本語フォントは、どのPCで開いても同じ見た目になるように
# フォントファイルをPDFに埋め込む方式にしている。
# 書体は「BIZ UDPGothic」（Morisawa／SIL Open Font License 1.1）。
# 高齢の方や読み書きに困難のある方にも読みやすいよう設計された
# UD（ユニバーサルデザイン）フォントで、Windows等にも標準搭載されている定番書体。
# Regular／Boldの2書体を実際に埋め込むことで、今までの「同じ書体を少しずらして
# 重ね書きする疑似太字」をやめ、本物の太字を使えるようにしている。
#
# PyInstallerでexe化した場合、同梱データはsys._MEIPASS（展開先）に
# 置かれ、__file__ベースの場所とは一致しないことがあるため、
# frozen時はそちらを優先して探す。
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _THIS_DIR = sys._MEIPASS
else:
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSETS_DIR = os.path.join(_THIS_DIR, "assets")
_FONT_REGULAR_PATH = os.path.join(_ASSETS_DIR, "BIZUDPGothic-Regular.ttf")
_FONT_BOLD_PATH = os.path.join(_ASSETS_DIR, "BIZUDPGothic-Bold.ttf")

FONT_REGULAR = "BIZUDPGothic"
FONT_BOLD = "BIZUDPGothic-Bold"

if FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
    if os.path.exists(_FONT_REGULAR_PATH) and os.path.exists(_FONT_BOLD_PATH):
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, _FONT_REGULAR_PATH))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, _FONT_BOLD_PATH))
        pdfmetrics.registerFontFamily(FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD)
    else:
        # フォントファイルが見つからない場合は、PDFビューア側のフォントに頼る
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        FONT_REGULAR = "HeiseiMin-W3"
        FONT_BOLD = "HeiseiKakuGo-W5"
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_REGULAR))
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_BOLD))

# ------------------------------------------------------------------
# 配色（アクセントカラー）
# ------------------------------------------------------------------
# 本文はどの書類も高コントラストな黒に統一し（色文字は逆に読みにくいため）、
# タイトル・見出し帯・重要な金額など「目印になる場所」だけに色を使う。
# 請求書＝青、領収証＝緑（アプリ画面の「請求書PDFを作成する」「領収証PDFを作成する」
# ボタンの色と揃えている）。
COLOR_TEXT = colors.HexColor("#1a1a1a")
COLOR_INVOICE_ACCENT = colors.HexColor("#1a56c4")
COLOR_INVOICE_TINT = colors.HexColor("#e8f0fc")
COLOR_RECEIPT_ACCENT = colors.HexColor("#157a3d")
COLOR_RECEIPT_TINT = colors.HexColor("#e6f4ea")

PAGE_W, PAGE_H = A4
MARGIN_L = 15 * 2.83465  # 15mm を pt に
MARGIN_R = 15 * 2.83465
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R


def to_reiwa(dt: datetime.date) -> str:
    reiwa_year = dt.year - 2018
    if dt.year < 2019:
        return f"{dt.year}年{dt.month}月{dt.day}日"
    if reiwa_year == 1:
        return f"令和元年{dt.month}月{dt.day}日"
    return f"令和{reiwa_year}年{dt.month}月{dt.day}日"


def fmt_yen(v):
    try:
        return "￥{:,}".format(int(round(float(v))))
    except Exception:
        return "￥0"


def spaced(text, gap="　"):
    """文字の間に全角スペースを入れて、見出し風に広げる。"""
    return gap.join(list(text))


def _draw_title(c, text, accent_color):
    """書類タイトル（「請求書」「領収証」）と、その下のアクセントラインを描く。"""
    y = PAGE_H - 20 * 2.83465
    c.setFillColor(accent_color)
    c.setFont(FONT_BOLD, 25)
    c.drawCentredString(PAGE_W / 2, y, spaced(text))
    c.setFillColor(COLOR_TEXT)
    # タイトル下のアクセントライン（帯）
    line_y = y - 12
    c.setStrokeColor(accent_color)
    c.setLineWidth(2)
    c.line(PAGE_W / 2 - 90, line_y, PAGE_W / 2 + 90, line_y)
    c.setStrokeColor(colors.black)
    return y - 40


def _draw_destination_block(c, x0, y_top, data, honorific="御中", name_font_size=16):
    """宛先情報（会社名・敬称・住所・電話・FAX）を左寄せで描画する。
    請求書・領収証で共通して使う。描画後のy座標を返す。"""
    y = y_top
    c.setFont(FONT_BOLD, name_font_size)
    dest_name = data.get("dest_name", "")
    c.drawString(x0, y, dest_name)
    text_w = c.stringWidth(dest_name, FONT_BOLD, name_font_size)
    c.drawString(x0 + text_w + 14, y, honorific)
    y -= 22

    c.setFont(FONT_REGULAR, 11.5)
    if data.get("dest_zip"):
        c.drawString(x0, y, f"〒{data['dest_zip']}　{data.get('dest_addr', '')}")
        y -= 16.5
    elif data.get("dest_addr"):
        c.drawString(x0, y, data.get("dest_addr", ""))
        y -= 16.5
    if data.get("dest_tel"):
        c.drawString(x0, y, f"電話　{data['dest_tel']}")
        y -= 16.5
    if data.get("dest_fax"):
        c.drawString(x0, y, f"FAX　{data['dest_fax']}")
        y -= 16.5
    return y


def _draw_issuer_block(c, x1, y_top, data):
    """発行元情報（住所・名称・印影・代表者・電話）を右寄せで描画する。
    請求書・領収証で共通して使う。描画後のy座標を返す。"""
    y = y_top
    if not data.get("show_issuer_block", True):
        return y

    issuer_zip = data.get("issuer_zip", "")
    issuer_addr = data.get("issuer_address", "")
    issuer_name = data.get("issuer_name", "")
    issuer_rep = data.get("issuer_representative", "")
    issuer_tel = data.get("issuer_tel", "")

    c.setFont(FONT_REGULAR, 10.5)
    if issuer_zip or issuer_addr:
        addr_line = f"〒{issuer_zip}　{issuer_addr}" if issuer_zip else issuer_addr
        c.drawRightString(x1, y, addr_line)
        y -= 18

    if issuer_name:
        name_y = y
        c.setFont(FONT_BOLD, 13)
        c.drawRightString(x1, name_y, issuer_name)

        # 会社印を、事務所の名前の上に重ねて印字
        seal_path = data.get("seal_path")
        if seal_path and os.path.exists(seal_path):
            try:
                img = ImageReader(seal_path)
                iw, ih = img.getSize()
                seal_size = 36
                name_w = c.stringWidth(issuer_name, FONT_BOLD, 13)
                seal_x = x1 - (name_w / 2) - (seal_size / 2)
                seal_y = name_y - 7
                c.saveState()
                c.drawImage(
                    img, seal_x, seal_y, width=seal_size, height=seal_size * ih / iw,
                    mask="auto", preserveAspectRatio=True,
                )
                c.restoreState()
            except Exception:
                pass
        y -= 20

    if issuer_rep:
        c.setFont(FONT_REGULAR, 13)
        c.drawRightString(x1, y, issuer_rep)
        y -= 19

    if issuer_tel:
        c.setFont(FONT_REGULAR, 10.5)
        c.drawRightString(x1, y, f"電話　{issuer_tel}")
        y -= 15.5

    return y


def _draw_item_table(c, x0, x1, y_top, items, show_note, accent_color, tint_color, min_rows=10):
    """品目の明細テーブル（日付・品名・数量・単価・金額・消費税・摘要）を描画する。
    請求書・領収証で共通して使う。描画後のy座標を返す。"""
    content_w = x1 - x0
    # 列幅は、文字サイズを大きくしても金額が枠からはみ出さないよう
    # 実際の文字幅（￥9,999,999まで）を基準に決めている。
    note_w = 60
    fixed_w = 48 + 34 + 74 + 78 + 62 + (note_w if show_note else 0)
    name_w = content_w - fixed_w
    if show_note:
        col_widths = [48, name_w, 34, 74, 78, 62, note_w]
        headers = ["日付", "品　名", "数量", "単価", "金額", "消費税", "摘要"]
        left_align_cols = (1, 6)
    else:
        # 摘要欄を表示しない設定の場合、その分の幅は品名欄にまわす
        col_widths = [48, name_w, 34, 74, 78, 62]
        headers = ["日付", "品　名", "数量", "単価", "金額", "消費税"]
        left_align_cols = (1,)
    row_h = 22
    n_rows = max(min_rows, len(items) + 2)
    table_top = y_top
    table_h = row_h * (n_rows + 2)  # +ヘッダー行 +合計行
    table_bottom = table_top - table_h

    xc = x0
    xs = [x0]
    for w in col_widths:
        xc += w
        xs.append(xc)

    # ヘッダー行の背景（見出し帯）
    header_y = table_top - row_h
    c.setFillColor(tint_color)
    c.rect(x0, header_y, content_w, row_h, stroke=0, fill=1)
    c.setFillColor(COLOR_TEXT)

    c.setLineWidth(0.8)
    # 外枠
    c.rect(x0, table_bottom, content_w, table_h, stroke=1, fill=0)

    # 縦線
    for xline in xs[1:-1]:
        c.line(xline, table_bottom, xline, table_top)

    # ヘッダー文字
    c.line(x0, header_y, x1, header_y)
    c.setFont(FONT_BOLD, 11)
    for i, htext in enumerate(headers):
        cx = (xs[i] + xs[i + 1]) / 2
        c.drawCentredString(cx, header_y + 7, htext)

    # データ行
    c.setFont(FONT_REGULAR, 11)
    cur_y = header_y
    for row_idx in range(n_rows):
        row_bottom = cur_y - row_h
        c.line(x0, row_bottom, x1, row_bottom)
        if row_idx < len(items):
            it = items[row_idx]
            vals = [
                it.get("date", ""),
                it.get("name", ""),
                it.get("qty", ""),
                (fmt_yen(it["price"]) if it.get("price") not in (None, "") else ""),
                fmt_yen(it.get("amount", 0)),
                (fmt_yen(it["tax"]) if it.get("tax") else ""),
            ]
            if show_note:
                vals.append(it.get("note", ""))
            for i, v in enumerate(vals):
                cx0, cx1 = xs[i], xs[i + 1]
                if i in left_align_cols:  # 品名・摘要は左寄せ
                    c.drawString(cx0 + 4, row_bottom + 7, str(v)[:26])
                else:
                    c.drawCentredString((cx0 + cx1) / 2, row_bottom + 7, str(v))
        cur_y = row_bottom

    # 合計行
    total_row_top = cur_y
    total_row_bottom = total_row_top - row_h
    c.line(x0, total_row_bottom, x1, total_row_bottom)
    c.setFont(FONT_BOLD, 12)
    c.drawCentredString((xs[0] + xs[1]) / 2, total_row_bottom + 7, "合計")
    total_amount = sum(
        float(it.get("amount", 0) or 0) + float(it.get("tax") or 0) for it in items
    )
    c.setFillColor(accent_color)
    c.drawRightString(xs[5] - 4, total_row_bottom + 7, fmt_yen(total_amount))
    c.setFillColor(COLOR_TEXT)

    return total_row_bottom - 26


def build_invoice_pdf(save_path, data: dict):
    c = canvas.Canvas(save_path, pagesize=A4)
    c.setTitle("請求書")
    c.setFillColor(COLOR_TEXT)

    x0 = MARGIN_L
    x1 = PAGE_W - MARGIN_R

    # ---------------- タイトル ----------------
    y = _draw_title(c, "請求書", COLOR_INVOICE_ACCENT)

    # ---------------- 請求書番号（あれば、日付の上に表示） ----------------
    if data.get("invoice_number"):
        c.setFont(FONT_REGULAR, 11)
        c.drawRightString(x1, y, f"No. {data['invoice_number']}")
        y -= 17

    # ---------------- 発行日（右上） ----------------
    date_str = to_reiwa(data["issue_date"])
    c.setFont(FONT_REGULAR, 12)
    c.drawRightString(x1, y, date_str)
    y -= 24

    block_top = y  # 左：宛先ブロック／右：請求元プロファイルブロック、共通の開始位置

    # ---------------- 宛先 + 御中（左側） ----------------
    y_left = _draw_destination_block(c, x0, block_top, data, honorific="御中", name_font_size=16)

    # ---------------- 請求元プロファイル（右側、日付の下） ----------------
    y_right = _draw_issuer_block(c, x1, block_top, data)

    y = min(y_left, y_right)
    y -= 12

    c.setFont(FONT_REGULAR, 12)
    c.drawString(x0, y, "下記の通りご請求申し上げます")
    y -= 24

    # ---------------- 税込合計金額 ----------------
    c.setFont(FONT_BOLD, 13)
    c.drawString(x0, y, "税込合計金額　")
    label_w = c.stringWidth("税込合計金額　", FONT_BOLD, 13)
    c.setFillColor(COLOR_INVOICE_ACCENT)
    c.setFont(FONT_BOLD, 16)
    c.drawString(x0 + label_w, y - 1, fmt_yen(data.get("total", 0)))
    c.setFillColor(COLOR_TEXT)
    y -= 22

    # ---------------- 明細テーブル ----------------
    y = _draw_item_table(
        c, x0, x1, y, data.get("items", []), data.get("show_note_column", True),
        COLOR_INVOICE_ACCENT, COLOR_INVOICE_TINT,
    )

    # ---------------- 備考欄 ----------------
    remarks_h = 48
    c.setFont(FONT_BOLD, 11.5)
    c.drawString(x0, y, "備考欄")
    c.rect(x0, y - remarks_h - 4, CONTENT_W, remarks_h, stroke=1, fill=0)
    if data.get("remarks"):
        c.setFont(FONT_REGULAR, 10.5)
        _draw_wrapped_text(c, data["remarks"], x0 + 6, y - 17, CONTENT_W - 12, 13.5, FONT_REGULAR, 10.5)
    y = y - remarks_h - 26

    # ---------------- 振込先 ----------------
    c.setFont(FONT_BOLD, 12.5)
    c.drawString(x0, y, "振込先")
    y -= 18
    c.setFont(FONT_REGULAR, 11)
    if data.get("bank_holder1"):
        c.drawString(x0 + 20, y, f"名義人：{data['bank_holder1']}")
        y -= 16.5
    if data.get("bank_holder2"):
        c.drawString(x0 + 20, y, data["bank_holder2"])
        y -= 16.5

    banks = data.get("banks", [])
    if banks:
        y -= 4
        b_col_widths = [140, 90, 55, 60, CONTENT_W - 140 - 90 - 55 - 60]
        b_headers = ["金融機関名", "支店名", "店番", "口座種類", "口座番号"]
        b_row_h = 22
        b_table_top = y
        b_table_h = b_row_h * (len(banks) + 1)
        b_table_bottom = b_table_top - b_table_h

        bxc = x0
        bxs = [x0]
        for w in b_col_widths:
            bxc += w
            bxs.append(bxc)

        header_y2 = b_table_top - b_row_h
        c.setFillColor(COLOR_INVOICE_TINT)
        c.rect(x0, header_y2, CONTENT_W, b_row_h, stroke=0, fill=1)
        c.setFillColor(COLOR_TEXT)

        c.rect(x0, b_table_bottom, CONTENT_W, b_table_h, stroke=1, fill=0)
        for xline in bxs[1:-1]:
            c.line(xline, b_table_bottom, xline, b_table_top)

        c.line(x0, header_y2, x1, header_y2)
        c.setFont(FONT_BOLD, 11)
        for i, htext in enumerate(b_headers):
            cx = (bxs[i] + bxs[i + 1]) / 2
            c.drawCentredString(cx, header_y2 + 7, htext)

        c.setFont(FONT_REGULAR, 11)
        cur_y2 = header_y2
        for bank in banks:
            row_bottom = cur_y2 - b_row_h
            c.line(x0, row_bottom, x1, row_bottom)
            vals = [bank.get("name", ""), bank.get("branch", ""), bank.get("code", ""),
                    bank.get("type", ""), bank.get("number", "")]
            for i, v in enumerate(vals):
                cx = (bxs[i] + bxs[i + 1]) / 2
                c.drawCentredString(cx, row_bottom + 7, str(v))
            cur_y2 = row_bottom
        y = b_table_bottom - 10

    c.showPage()
    c.save()


def build_receipt_pdf(save_path, data: dict):
    """領収証PDFを作成する。全体の構成は請求書と共通（タイトル→No./日付→
    宛先ブロック（左）＋発行元ブロック（右）→本文）にしている。

    data の主なキー：
      issue_date（領収日）, invoice_number（請求書と共通の番号・任意）,
      dest_name/dest_zip/dest_addr/dest_tel/dest_fax（宛先。請求書と共通）,
      total（金額）, tax_total（内消費税額・任意）,
      remarks（但し書き）, issuer_*（発行元情報）, seal_path, show_issuer_block
    """
    c = canvas.Canvas(save_path, pagesize=A4)
    c.setTitle("領収証")
    c.setFillColor(COLOR_TEXT)

    x0 = MARGIN_L
    x1 = PAGE_W - MARGIN_R

    # ---------------- タイトル ----------------
    y = _draw_title(c, "領収証", COLOR_RECEIPT_ACCENT)

    # ---------------- 番号（あれば、日付の上に表示） ----------------
    if data.get("invoice_number"):
        c.setFont(FONT_REGULAR, 11)
        c.drawRightString(x1, y, f"No. {data['invoice_number']}")
        y -= 17

    # ---------------- 領収日（右上） ----------------
    date_str = to_reiwa(data["issue_date"])
    c.setFont(FONT_REGULAR, 12)
    c.drawRightString(x1, y, date_str)
    y -= 24

    block_top = y  # 左：宛先ブロック／右：発行元プロファイルブロック、共通の開始位置（請求書と同じ構成）

    # ---------------- 宛先 + 様（左側） ----------------
    y_left = _draw_destination_block(c, x0, block_top, data, honorific="様", name_font_size=16)

    # ---------------- 発行元プロファイル（右側、日付の下） ----------------
    y_right = _draw_issuer_block(c, x1, block_top, data)

    y = min(y_left, y_right)
    y -= 16

    # ---------------- 金額ボックス ----------------
    total = data.get("total", 0)
    box_h = 50
    box_top = y
    c.setFillColor(COLOR_RECEIPT_TINT)
    c.rect(x0, box_top - box_h, CONTENT_W, box_h, stroke=0, fill=1)
    c.setFillColor(COLOR_TEXT)
    c.setStrokeColor(COLOR_RECEIPT_ACCENT)
    c.setLineWidth(1.6)
    c.rect(x0, box_top - box_h, CONTENT_W, box_h, stroke=1, fill=0)
    c.setStrokeColor(colors.black)
    c.setFont(FONT_BOLD, 13)
    c.drawString(x0 + 14, box_top - 20, "金額")
    amount_str = fmt_yen(total) + "－"
    c.setFillColor(COLOR_RECEIPT_ACCENT)
    c.setFont(FONT_BOLD, 23)
    c.drawRightString(x0 + CONTENT_W - 16, box_top - 34, amount_str)
    c.setFillColor(COLOR_TEXT)
    y = box_top - box_h - 18

    # ---------------- 内消費税額 ----------------
    tax_total = data.get("tax_total", 0)
    if tax_total:
        c.setFont(FONT_REGULAR, 10.5)
        c.drawRightString(x1, y, f"（内消費税等　{fmt_yen(tax_total)}）")
        y -= 21
    else:
        y -= 4

    # ---------------- 品目の内訳テーブル ----------------
    # 品目が未入力でもレイアウト確認ができるよう、常に表を表示する
    # （請求書のような10行固定ではなく、領収証らしく控えめな最低5行）。
    items = data.get("items", [])
    y -= 6
    y = _draw_item_table(
        c, x0, x1, y, items, data.get("show_note_column", True),
        COLOR_RECEIPT_ACCENT, COLOR_RECEIPT_TINT, min_rows=5,
    )

    # ---------------- 但し書き ----------------
    c.setFont(FONT_REGULAR, 12.5)
    kotogaki = data.get("remarks", "").strip() or "お品代"
    c.drawString(x0, y, f"但し　{kotogaki}として")
    y -= 21
    c.drawString(x0, y, "上記正に領収いたしました。")
    y -= 32

    stamp_top = y  # 収入印紙欄の開始位置

    # ---------------- 収入印紙欄（5万円以上の場合のみ） ----------------
    if total and float(total) >= 50000:
        stamp_w, stamp_h = 78, 98
        stamp_x = x0
        stamp_y = stamp_top - stamp_h
        c.setLineWidth(0.6)
        c.rect(stamp_x, stamp_y, stamp_w, stamp_h, stroke=1, fill=0)
        c.setFont(FONT_BOLD, 11)
        c.drawCentredString(stamp_x + stamp_w / 2, stamp_y + stamp_h - 19, "収入")
        c.drawCentredString(stamp_x + stamp_w / 2, stamp_y + stamp_h - 36, "印紙")
        c.setFont(FONT_REGULAR, 9)
        _draw_wrapped_text(
            c,
            "※5万円以上の受取りのため、印紙税法上、収入印紙の貼付・消印が必要です（貼付は発行者にて行ってください）。",
            stamp_x + stamp_w + 12, stamp_top - 15,
            CONTENT_W - stamp_w - 12, 12.5, FONT_REGULAR, 9,
        )

    c.showPage()
    c.save()


def _draw_wrapped_text(c, text, x, y, max_width, line_height, font, size):
    c.setFont(font, size)
    line = ""
    cur_y = y
    for ch in text:
        if ch == "\n":
            c.drawString(x, cur_y, line)
            line = ""
            cur_y -= line_height
            continue
        test = line + ch
        if c.stringWidth(test, font, size) > max_width:
            c.drawString(x, cur_y, line)
            line = ch
            cur_y -= line_height
        else:
            line = test
    if line:
        c.drawString(x, cur_y, line)
