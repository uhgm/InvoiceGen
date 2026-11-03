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
                # 欄に収まらない長さの文字は、自動で小さくして枠からはみ出さないようにする
                if i in left_align_cols:  # 品名・摘要は左寄せ。長ければ2行に折り返す
                    _draw_cell_text(c, v, cx0 + 4, row_bottom, row_h, cx1 - cx0 - 8, FONT_REGULAR, 11)
                else:
                    _draw_fitted(c, v, (cx0 + cx1) / 2, row_bottom + 7, cx1 - cx0 - 6,
                                 FONT_REGULAR, 11, align="center")
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
    # 合計は金額欄の右端に揃える。金額が大きく欄に収まらないときは、左隣の単価欄まで使う
    _draw_fitted(c, fmt_yen(total_amount), xs[5] - 4, total_row_bottom + 7,
                 xs[5] - xs[3] - 8, FONT_BOLD, 12, align="right")
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

    # ---------------- 収入印紙欄（5万円以上の場合のみ） ----------------
    _draw_revenue_stamp_box(c, x0, y, total)

    c.showPage()
    c.save()


def _draw_revenue_stamp_box(c, x0, stamp_top, total):
    """受取金額が5万円以上のときだけ、収入印紙を貼る枠と注意書きを描く。
    標準の領収証・以前のシステム風の領収書で共通して使う。"""
    if not total or float(total) < 50000:
        return
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


# ------------------------------------------------------------------
# 以前のシステムと同じ書式（classic）
# ------------------------------------------------------------------
# 現場で使われていた既存システム（Excel様式）の請求書・領収書を見本に、
# 項目の並び・配置・表の形をそろえた書式。見本どおり色は使わず黒一色にしている。
# 標準の書式（build_invoice_pdf／build_receipt_pdf）とは別に用意しており、
# 画面下の「PDFの書式」で切り替える。
CLASSIC_ROW_H = 19
CLASSIC_MIN_ROWS = 9  # 見本と同じく、品目が少なくても9行分の枠を用意する
CLASSIC_SEAL_SIZE = 80  # 印影は見本どおり大きめに、発行元の名称・住所・電話に重ねる
# 明細表の列幅（表全体の幅に対する比率）。見本の列幅を測ってそろえている。
# 順番は 日付・品名・数量・単価・金額・消費税・摘要。
# 請求書は品名欄が広く、領収書は摘要欄が広い（どちらも見本どおり）。
CLASSIC_INVOICE_COLS = [0.092, 0.281, 0.086, 0.107, 0.155, 0.141, 0.138]
CLASSIC_RECEIPT_COLS = [0.125, 0.125, 0.125, 0.125, 0.125, 0.125, 0.25]


def fmt_num(v):
    """見本の表に合わせて、円マークなし・3桁区切りの数字にする。"""
    try:
        return "{:,}".format(int(round(float(v))))
    except Exception:
        return ""


def _fit_text(c, text, max_width, font, size, min_size=5, truncate=False):
    """枠に収まるよう文字を小さくする。(文字列, 文字サイズ) を返す。
    金額などの数字は1桁でも欠けると内容が変わってしまうため、既定では文字を削らない
    （最小サイズでも入らないときは、そのまま少しはみ出す）。
    truncate=True のときだけ、入らない分を削って末尾を「…」にする。"""
    text = str(text)
    while size > min_size and c.stringWidth(text, font, size) > max_width:
        size -= 0.25
    if truncate and c.stringWidth(text, font, size) > max_width:
        while text and c.stringWidth(text + "…", font, size) > max_width:
            text = text[:-1]
        text += "…"
    return text, size


def _draw_fitted(c, text, x, y, max_width, font, size, align="left"):
    text, size = _fit_text(c, text, max_width, font, size)
    c.setFont(font, size)
    if align == "right":
        c.drawRightString(x, y, text)
    elif align == "center":
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)


def _draw_cell_text(c, text, x, row_bottom, row_h, max_width, font, size):
    """表の品名・摘要欄の文字を左寄せで描く。少し縮めても1行に入らなければ
    2行に折り返し、それでも入らないときだけ末尾を「…」にする。"""
    text = str(text)
    one_line, one_size = _fit_text(c, text, max_width, font, size, min_size=size * 0.8)
    if c.stringWidth(one_line, font, one_size) <= max_width:
        c.setFont(font, one_size)
        c.drawString(x, row_bottom + (row_h - 0.72 * one_size) / 2, one_line)
        return

    s2 = min(size, row_h / 2.5)
    while True:
        cut = len(text)
        while cut > 1 and c.stringWidth(text[:cut], font, s2) > max_width:
            cut -= 1
        line1, line2 = text[:cut], text[cut:]
        if c.stringWidth(line2, font, s2) <= max_width or s2 <= 5:
            break
        s2 -= 0.25
    line2, _ = _fit_text(c, line2, max_width, font, s2, min_size=s2, truncate=True)
    c.setFont(font, s2)
    # 2行のまとまりが行の上下中央に来る位置
    base1 = row_bottom + row_h / 2 + 0.19 * s2
    c.drawString(x, base1, line1)
    c.drawString(x, base1 - s2 * 1.1, line2)


def _draw_distributed(c, text, x_left, x_right, y, font, size):
    """Excelの「均等割り付け」のように、文字の間隔を広げて
    x_left〜x_right の幅いっぱいに描く（見本の発行元名称・電話番号の見た目）。"""
    text, size = _fit_text(c, text, x_right - x_left, font, size)
    c.setFont(font, size)
    w = c.stringWidth(text, font, size)
    if len(text) < 2:
        c.drawString(x_left, y, text)
        return
    gap = (x_right - x_left - w) / (len(text) - 1)
    c.drawString(x_left, y, text, charSpace=gap)


def _classic_era_year(dt: datetime.date) -> str:
    """見本の日付欄は「令和」を省いた「8年」の形なので、年の数字だけを返す。"""
    if dt.year < 2019:
        return str(dt.year)
    if dt.year == 2019:
        return "元"
    return str(dt.year - 2018)


def _draw_classic_header(c, title, message, data):
    """タイトル→日付→宛先→発行元→「下記の通り〜」→税込合計金額の枠 までを描く。
    請求書・領収書で共通。描画後のy座標（明細表の上端）を返す。"""
    x0 = MARGIN_L
    x1 = PAGE_W - MARGIN_R

    # ---------------- タイトル ----------------
    y = PAGE_H - 72
    c.setFont(FONT_REGULAR, 22)
    c.drawCentredString(PAGE_W / 2, y, title)
    y -= 22

    # ---------------- 番号（あれば左側）・日付（右上） ----------------
    # 見本の日付は「8年　10月　1日」と、年・月・日が離れて並んでいる
    if data.get("invoice_number"):
        c.setFont(FONT_REGULAR, 10.5)
        c.drawString(x0, y, f"No. {data['invoice_number']}")
    dt = data["issue_date"]
    c.setFont(FONT_REGULAR, 12)
    c.drawRightString(x1 - 150, y, f"{_classic_era_year(dt)}年")
    c.drawRightString(x1 - 75, y, f"{dt.month}月")
    c.drawRightString(x1, y, f"{dt.day}日")
    y -= 27

    # ---------------- 宛先 + 御中（左側。見本は住所なし、名前だけ） ----------------
    c.setFont(FONT_REGULAR, 14)
    dest_name = data.get("dest_name", "")
    c.drawString(x0, y, dest_name)
    c.drawString(x0 + c.stringWidth(dest_name, FONT_REGULAR, 14) + 14, y, "御中")
    y -= 25

    # ---------------- 発行元（右側、宛先の下） ----------------
    y = _draw_classic_issuer_block(c, x0 + CONTENT_W * 0.5, x1, y, data)

    # ---------------- 「下記の通り〜」 ----------------
    c.setFont(FONT_REGULAR, 12)
    c.drawString(x0, y, message)
    y -= 10

    # ---------------- 税込合計金額（枠囲み） ----------------
    box_h = 25
    box_w = CONTENT_W * 0.567
    c.setLineWidth(1.2)
    c.rect(x0, y - box_h, box_w, box_h, stroke=1, fill=0)
    c.setFont(FONT_REGULAR, 13)
    c.drawString(x0 + 4, y - 18, f"税込合計金額{fmt_yen(data.get('total', 0))}")
    return y - box_h - 23


def _draw_classic_issuer_block(c, x_left, x1, y_top, data):
    """発行元（名称・住所・電話・FAX）を、見本と同じく右半分に左寄せで描く。
    名称と電話・FAX番号は均等割り付け、印影はその上に大きく重ねる。
    描画後のy座標を返す。"""
    if not data.get("show_issuer_block", True):
        return y_top
    line_h = 25
    label_w = 50  # 「電話」「FAX」の見出しぶんの幅
    name_y = y = y_top

    if data.get("issuer_name"):
        _draw_distributed(c, data["issuer_name"], x_left, x1, y, FONT_REGULAR, 13)
        y -= line_h

    issuer_zip = data.get("issuer_zip", "")
    issuer_addr = data.get("issuer_address", "")
    if issuer_zip or issuer_addr:
        addr_line = f"〒{issuer_zip}{issuer_addr}" if issuer_zip else issuer_addr
        _draw_fitted(c, addr_line, x_left, y, x1 - x_left, FONT_REGULAR, 12)
        y -= line_h

    for label, key in (("電話", "issuer_tel"), ("FAX", "issuer_fax")):
        if data.get(key):
            c.setFont(FONT_REGULAR, 12)
            c.drawString(x_left, y, label)
            _draw_distributed(c, data[key], x_left + label_w, x1, y, FONT_REGULAR, 12)
            y -= line_h

    seal_path = data.get("seal_path")
    if seal_path and os.path.exists(seal_path):
        try:
            img = ImageReader(seal_path)
            iw, ih = img.getSize()
            seal_w = CLASSIC_SEAL_SIZE
            seal_h = seal_w * ih / iw
            # 見本では、印影の中心が名称の右寄り・名称と住所の間あたりにある
            seal_cx = x1 - 64
            seal_cy = name_y - 15
            c.drawImage(
                img, seal_cx - seal_w / 2, seal_cy - seal_h / 2, width=seal_w, height=seal_h,
                mask="auto", preserveAspectRatio=True,
            )
        except Exception:
            pass

    return y - 1


def _draw_classic_item_table(c, x0, x1, y_top, items, show_note, col_ratios):
    """見本と同じ形の明細表（日付・品名・数量・単価・金額・消費税・摘要）と、
    そのすぐ下にくっついた備考欄の枠を描く。表の下端のy座標を返す。"""
    content_w = x1 - x0
    col_widths = [content_w * r for r in col_ratios]
    headers = ["日付", "品　名", "数量", "単価", "金額", "消費税", "摘要"]
    if not show_note:
        # 摘要欄を表示しない設定の場合、その分の幅は品名欄にまわす
        col_widths[1] += col_widths.pop()
        headers.pop()

    xs = [x0]
    for w in col_widths:
        xs.append(xs[-1] + w)

    row_h = CLASSIC_ROW_H
    n_rows = max(CLASSIC_MIN_ROWS, len(items))
    table_h = row_h * (n_rows + 2)  # +ヘッダー行 +合計行
    table_bottom = y_top - table_h

    c.setLineWidth(1.2)
    c.rect(x0, table_bottom, content_w, table_h, stroke=1, fill=0)
    c.setLineWidth(0.6)
    for xline in xs[1:-1]:
        c.line(xline, table_bottom, xline, y_top)

    header_y = y_top - row_h
    c.line(x0, header_y, x1, header_y)
    for i, htext in enumerate(headers):
        _draw_fitted(c, htext, (xs[i] + xs[i + 1]) / 2, header_y + 5.5,
                     col_widths[i] - 4, FONT_REGULAR, 10.5, align="center")

    # 品名・摘要は左寄せ、それ以外（日付・数字）は右寄せ（見本どおり）
    left_align_cols = (1, 6)
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
                fmt_num(it["price"]) if it.get("price") not in (None, "") else "",
                fmt_num(it.get("amount", 0)),
                fmt_num(it["tax"]) if it.get("tax") else "",
            ]
            if show_note:
                vals.append(it.get("note", ""))
            for i, v in enumerate(vals):
                max_w = col_widths[i] - 6
                if i in left_align_cols:
                    _draw_cell_text(c, v, xs[i] + 3, row_bottom, row_h, max_w, FONT_REGULAR, 10.5)
                else:
                    _draw_fitted(c, v, xs[i + 1] - 3, row_bottom + 5.5, max_w, FONT_REGULAR, 10.5,
                                 align="right")
        cur_y = row_bottom

    # 合計行：金額欄に金額の合計、消費税欄に消費税の合計（あれば）
    total_bottom = cur_y - row_h
    _draw_fitted(c, "合計", (xs[0] + xs[1]) / 2, total_bottom + 5.5,
                 col_widths[0] - 4, FONT_REGULAR, 10.5, align="center")
    amount_sum = sum(float(it.get("amount", 0) or 0) for it in items)
    tax_sum = sum(float(it.get("tax") or 0) for it in items)
    _draw_fitted(c, fmt_num(amount_sum), xs[5] - 3, total_bottom + 5.5,
                 col_widths[4] - 6, FONT_REGULAR, 10.5, align="right")
    if tax_sum:
        _draw_fitted(c, fmt_num(tax_sum), xs[6] - 3, total_bottom + 5.5,
                     col_widths[5] - 6, FONT_REGULAR, 10.5, align="right")
    return total_bottom


def _draw_classic_remarks_box(c, x0, y_top, remarks):
    """明細表のすぐ下に、表と同じ幅の備考欄を描く。下端のy座標を返す。"""
    box_h = 44
    c.setLineWidth(1.2)
    c.rect(x0, y_top - box_h, CONTENT_W, box_h, stroke=1, fill=0)
    c.setFont(FONT_REGULAR, 10.5)
    c.drawString(x0 + 3, y_top - 13, "備考欄")
    if remarks:
        _draw_wrapped_text(c, remarks, x0 + 6, y_top - 27, CONTENT_W - 12, 12.5, FONT_REGULAR, 10)
    return y_top - box_h


def build_invoice_pdf_classic(save_path, data: dict):
    """以前のシステムと同じ書式の請求書PDFを作成する。data は build_invoice_pdf と同じ
    （発行元FAXの issuer_fax だけ、この書式でのみ使う）。"""
    c = canvas.Canvas(save_path, pagesize=A4)
    c.setTitle("請求書")
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    x0 = MARGIN_L
    x1 = PAGE_W - MARGIN_R

    y = _draw_classic_header(c, spaced("請求書"), "下記の通りご請求申し上げます", data)
    y = _draw_classic_item_table(
        c, x0, x1, y, data.get("items", []), data.get("show_note_column", True),
        CLASSIC_INVOICE_COLS,
    )
    y = _draw_classic_remarks_box(c, x0, y, data.get("remarks", ""))
    y -= 20

    # ---------------- 振込先 ----------------
    # 見本：「振込先　名義人（各行共通）　〇〇」の下に、字下げして住所・電話、その下に口座の表
    indent = x0 + CONTENT_W * 0.105
    banks = data.get("banks", [])
    c.setFont(FONT_REGULAR, 12)
    c.drawString(x0, y, "振込先")
    holder_label = "名義人（各行共通）" if len(banks) > 1 else "名義人"
    label_x = x0 + c.stringWidth("振込先", FONT_REGULAR, 12) + 8
    c.drawString(label_x, y, holder_label)
    if data.get("bank_holder1"):
        holder_x = label_x + c.stringWidth(holder_label, FONT_REGULAR, 12) + 16
        _draw_fitted(c, data["bank_holder1"], holder_x, y, x1 - holder_x, FONT_REGULAR, 12)
    if data.get("bank_holder2"):
        y -= 24
        _draw_fitted(c, data["bank_holder2"], indent, y, x1 - indent, FONT_REGULAR, 12)
    y -= 10

    if banks:
        b_ratios = [0.363, 0.112, 0.137, 0.2, 0.188]
        b_width = CONTENT_W * 0.764
        b_widths = [b_width * r for r in b_ratios]
        bxs = [indent]
        for w in b_widths:
            bxs.append(bxs[-1] + w)
        b_x1 = bxs[-1]
        b_row_h = CLASSIC_ROW_H
        b_table_h = b_row_h * (len(banks) + 1)
        b_bottom = y - b_table_h

        c.setLineWidth(1.2)
        c.rect(indent, b_bottom, b_width, b_table_h, stroke=1, fill=0)
        c.setLineWidth(0.6)
        for xline in bxs[1:-1]:
            c.line(xline, b_bottom, xline, y)

        # 見出し・データともに左寄せ。口座番号だけ右寄せ（見本どおり）
        cur_y = y
        rows = [["金融機関名", "支店名", "店番", "口座種類", "口座番号"]]
        rows += [[b.get("name", ""), b.get("branch", ""), b.get("code", ""),
                  b.get("type", ""), b.get("number", "")] for b in banks]
        for r_idx, vals in enumerate(rows):
            row_bottom = cur_y - b_row_h
            if r_idx < len(rows) - 1:
                c.line(indent, row_bottom, b_x1, row_bottom)
            for i, v in enumerate(vals):
                if i == 4 and r_idx > 0:
                    _draw_fitted(c, v, bxs[i + 1] - 3, row_bottom + 5.5, b_widths[i] - 6,
                                 FONT_REGULAR, 10.5, align="right")
                else:
                    _draw_fitted(c, v, bxs[i] + 3, row_bottom + 5.5, b_widths[i] - 6,
                                 FONT_REGULAR, 10.5)
            cur_y = row_bottom

    c.showPage()
    c.save()


def build_receipt_pdf_classic(save_path, data: dict):
    """以前のシステムと同じ書式の領収書PDFを作成する。data は build_receipt_pdf と同じ。
    見本には但し書きがないため、data["remarks"]（但し書き）はこの書式では印字しない。"""
    c = canvas.Canvas(save_path, pagesize=A4)
    c.setTitle("領収書")
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    x0 = MARGIN_L
    x1 = PAGE_W - MARGIN_R

    y = _draw_classic_header(c, "領収書", "下記の通り領収いたしました", data)
    y = _draw_classic_item_table(
        c, x0, x1, y, data.get("items", []), data.get("show_note_column", True),
        CLASSIC_RECEIPT_COLS,
    )
    y = _draw_classic_remarks_box(c, x0, y, "")

    # ---------------- 収入印紙欄（5万円以上の場合のみ） ----------------
    _draw_revenue_stamp_box(c, x0, y - 24, data.get("total", 0))

    c.showPage()
    c.save()


def build_dummy_seal_png(save_path, text="見本之印", size_px=400):
    """出力テスト用の、正方形（1:1）の角印風の画像を作る。
    文字は角印と同じく、右の列から縦に読む並び（例：見本之印 → 右列「見本」・左列「之印」）。
    背景は透明なので、本物の印影画像と同じように文字の上に重ねられる。"""
    import math
    from PIL import Image, ImageDraw, ImageFont

    red = (200, 30, 40, 255)
    img = Image.new("RGBA", (size_px, size_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    border = size_px // 20
    draw.rectangle([border, border, size_px - border - 1, size_px - border - 1],
                   outline=red, width=border)

    cols = math.ceil(math.sqrt(len(text)))
    rows = math.ceil(len(text) / cols)
    inner = size_px - border * 4
    cell_w, cell_h = inner / cols, inner / rows
    font_path = _FONT_BOLD_PATH if os.path.exists(_FONT_BOLD_PATH) else None
    font_px = int(min(cell_w, cell_h) * 0.86)
    font = ImageFont.truetype(font_path, font_px) if font_path else ImageFont.load_default()
    for i, ch in enumerate(text):
        col, row = divmod(i, rows)
        cx = size_px - border * 2 - cell_w * (col + 0.5)  # 右の列から並べる
        cy = border * 2 + cell_h * (row + 0.5)
        draw.text((cx, cy), ch, font=font, fill=red, anchor="mm")
    img.save(save_path)
    return save_path


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
