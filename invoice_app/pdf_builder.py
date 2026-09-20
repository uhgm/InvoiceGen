# -*- coding: utf-8 -*-
"""
請求書PDFの描画処理。
invoice_generator.py から呼び出される。
"""
import os
import datetime

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# 日本語フォントは、どのPCで開いても同じ見た目になるように
# フォントファイルをPDFに埋め込む方式にしている（IPAフォント／IPAフォントライセンスv1.0）。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_PATH = os.path.join(_THIS_DIR, "assets", "ipag.ttf")

FONT_NAME = "IPAGothic"
FONT_MIN = "IPAGothic"  # 現状は1書体のみ埋め込み、明朝の代わりにも同じ書体を使用

if not pdfmetrics.getRegisteredFontNames() or FONT_NAME not in pdfmetrics.getRegisteredFontNames():
    if os.path.exists(_FONT_PATH):
        pdfmetrics.registerFont(TTFont(FONT_NAME, _FONT_PATH))
    else:
        # フォントファイルが見つからない場合は、PDFビューア側のフォントに頼る
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        FONT_NAME = "HeiseiKakuGo-W5"
        FONT_MIN = "HeiseiMin-W3"
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_MIN))

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


def draw_bold_centred(c, x, y, text, font, size):
    """1書体しかない場合に、少しずらして重ね書きすることで太字風にする。"""
    c.setFont(font, size)
    for dx, dy in [(0, 0), (0.4, 0), (0, 0.4), (0.4, 0.4)]:
        c.drawCentredString(x + dx, y + dy, text)


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

    c.setFont(FONT_MIN, 9.5)
    if issuer_zip or issuer_addr:
        addr_line = f"〒{issuer_zip}　{issuer_addr}" if issuer_zip else issuer_addr
        c.drawRightString(x1, y, addr_line)
        y -= 17

    if issuer_name:
        name_y = y
        c.setFont(FONT_NAME, 12)
        c.drawRightString(x1, name_y, issuer_name)

        # 会社印を、事務所の名前の上に重ねて印字
        seal_path = data.get("seal_path")
        if seal_path and os.path.exists(seal_path):
            try:
                img = ImageReader(seal_path)
                iw, ih = img.getSize()
                seal_size = 36
                name_w = c.stringWidth(issuer_name, FONT_NAME, 12)
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
        y -= 18

    if issuer_rep:
        c.setFont(FONT_MIN, 9.5)
        c.drawRightString(x1, y, issuer_rep)
        y -= 14

    if issuer_tel:
        c.setFont(FONT_MIN, 9.5)
        c.drawRightString(x1, y, f"電話　{issuer_tel}")
        y -= 14

    return y


def build_invoice_pdf(save_path, data: dict):
    c = canvas.Canvas(save_path, pagesize=A4)
    c.setTitle("請求書")

    x0 = MARGIN_L
    x1 = PAGE_W - MARGIN_R
    y = PAGE_H - 20 * 2.83465

    # ---------------- タイトル ----------------
    draw_bold_centred(c, PAGE_W / 2, y, spaced("請求書"), FONT_NAME, 22)
    y -= 34

    # ---------------- 請求書番号（あれば、日付の上に表示） ----------------
    if data.get("invoice_number"):
        c.setFont(FONT_MIN, 10)
        c.drawRightString(x1, y, f"No. {data['invoice_number']}")
        y -= 16

    # ---------------- 発行日（右上） ----------------
    date_str = to_reiwa(data["issue_date"])
    c.setFont(FONT_MIN, 11)
    c.drawRightString(x1, y, date_str)
    y -= 22

    block_top = y  # 左：宛先ブロック／右：請求元プロファイルブロック、共通の開始位置

    # ---------------- 宛先 + 御中（左側） ----------------
    y_left = block_top
    c.setFont(FONT_NAME, 15)
    dest_name = data.get("dest_name", "")
    c.drawString(x0, y_left, dest_name)
    text_w = c.stringWidth(dest_name, FONT_NAME, 15)
    onchu_x = x0 + text_w + 14
    c.drawString(onchu_x, y_left, "御中")
    y_left -= 20

    c.setFont(FONT_MIN, 10.5)
    if data.get("dest_zip"):
        c.drawString(x0, y_left, f"〒{data['dest_zip']}　{data.get('dest_addr', '')}")
        y_left -= 15
    elif data.get("dest_addr"):
        c.drawString(x0, y_left, data.get("dest_addr", ""))
        y_left -= 15
    if data.get("dest_tel"):
        c.drawString(x0, y_left, f"電話　{data['dest_tel']}")
        y_left -= 15
    if data.get("dest_fax"):
        c.drawString(x0, y_left, f"FAX　{data['dest_fax']}")
        y_left -= 15

    # ---------------- 請求元プロファイル（右側、日付の下） ----------------
    y_right = _draw_issuer_block(c, x1, block_top, data)

    y = min(y_left, y_right)
    y -= 10

    c.setFont(FONT_MIN, 11)
    c.drawString(x0, y, "下記の通りご請求申し上げます")
    y -= 22

    # ---------------- 税込合計金額 ----------------
    c.setFont(FONT_NAME, 13)
    c.drawString(x0, y, f"税込合計金額　{fmt_yen(data.get('total', 0))}")
    y -= 20

    # ---------------- 明細テーブル ----------------
    table_top = y
    col_widths = [58, CONTENT_W - 58 - 40 - 60 - 70 - 55 - 90, 40, 60, 70, 55, 90]
    headers = ["日付", "品　名", "数量", "単価", "金額", "消費税", "摘要"]
    row_h = 20
    n_rows = max(10, len(data.get("items", [])) + 2)
    table_h = row_h * (n_rows + 2)  # +ヘッダー行 +合計行
    table_bottom = table_top - table_h

    c.setLineWidth(0.8)
    # 外枠
    c.rect(x0, table_bottom, CONTENT_W, table_h, stroke=1, fill=0)

    # 縦線
    xc = x0
    xs = [x0]
    for w in col_widths:
        xc += w
        xs.append(xc)
    for xline in xs[1:-1]:
        c.line(xline, table_bottom, xline, table_top)

    # ヘッダー行
    header_y = table_top - row_h
    c.line(x0, header_y, x1, header_y)
    c.setFont(FONT_NAME, 10)
    for i, htext in enumerate(headers):
        cx = (xs[i] + xs[i + 1]) / 2
        c.drawCentredString(cx, header_y + 6, htext)

    # データ行
    c.setFont(FONT_MIN, 10)
    cur_y = header_y
    items = data.get("items", [])
    for row_idx in range(n_rows):
        row_top = cur_y
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
                it.get("note", ""),
            ]
            for i, v in enumerate(vals):
                cx0, cx1 = xs[i], xs[i + 1]
                if i in (1, 6):  # 品名・摘要は左寄せ
                    c.drawString(cx0 + 4, row_bottom + 6, str(v)[:26])
                else:
                    c.drawCentredString((cx0 + cx1) / 2, row_bottom + 6, str(v))
        cur_y = row_bottom

    # 合計行
    total_row_top = cur_y
    total_row_bottom = total_row_top - row_h
    c.line(x0, total_row_bottom, x1, total_row_bottom)
    c.setFont(FONT_NAME, 11)
    c.drawCentredString((xs[0] + xs[1]) / 2, total_row_bottom + 6, "合計")
    total_amount = sum(
        float(it.get("amount", 0) or 0) + float(it.get("tax") or 0) for it in items
    )
    c.drawRightString(xs[5] - 4, total_row_bottom + 6, fmt_yen(total_amount))

    y = total_row_bottom - 24

    # ---------------- 備考欄 ----------------
    remarks_h = 46
    c.setFont(FONT_NAME, 10)
    c.drawString(x0, y, "備考欄")
    c.rect(x0, y - remarks_h - 4, CONTENT_W, remarks_h, stroke=1, fill=0)
    if data.get("remarks"):
        c.setFont(FONT_MIN, 9.5)
        _draw_wrapped_text(c, data["remarks"], x0 + 6, y - 16, CONTENT_W - 12, 12, FONT_MIN, 9.5)
    y = y - remarks_h - 24

    # ---------------- 振込先 ----------------
    c.setFont(FONT_NAME, 11)
    c.drawString(x0, y, "振込先")
    y -= 16
    c.setFont(FONT_MIN, 10)
    if data.get("bank_holder1"):
        c.drawString(x0 + 20, y, f"名義人：{data['bank_holder1']}")
        y -= 15
    if data.get("bank_holder2"):
        c.drawString(x0 + 20, y, data["bank_holder2"])
        y -= 15

    banks = data.get("banks", [])
    if banks:
        y -= 4
        b_col_widths = [140, 90, 55, 60, CONTENT_W - 140 - 90 - 55 - 60]
        b_headers = ["金融機関名", "支店名", "店番", "口座種類", "口座番号"]
        b_row_h = 20
        b_table_top = y
        b_table_h = b_row_h * (len(banks) + 1)
        b_table_bottom = b_table_top - b_table_h

        c.rect(x0, b_table_bottom, CONTENT_W, b_table_h, stroke=1, fill=0)
        bxc = x0
        bxs = [x0]
        for w in b_col_widths:
            bxc += w
            bxs.append(bxc)
        for xline in bxs[1:-1]:
            c.line(xline, b_table_bottom, xline, b_table_top)

        header_y2 = b_table_top - b_row_h
        c.line(x0, header_y2, x1, header_y2)
        c.setFont(FONT_NAME, 10)
        for i, htext in enumerate(b_headers):
            cx = (bxs[i] + bxs[i + 1]) / 2
            c.drawCentredString(cx, header_y2 + 6, htext)

        c.setFont(FONT_MIN, 10)
        cur_y2 = header_y2
        for bank in banks:
            row_bottom = cur_y2 - b_row_h
            c.line(x0, row_bottom, x1, row_bottom)
            vals = [bank.get("name", ""), bank.get("branch", ""), bank.get("code", ""),
                    bank.get("type", ""), bank.get("number", "")]
            for i, v in enumerate(vals):
                cx = (bxs[i] + bxs[i + 1]) / 2
                c.drawCentredString(cx, row_bottom + 6, str(v))
            cur_y2 = row_bottom
        y = b_table_bottom - 10

    c.showPage()
    c.save()


def build_receipt_pdf(save_path, data: dict):
    """領収証PDFを作成する。

    data の主なキー：
      issue_date（領収日）, invoice_number（請求書と共通の番号・任意）,
      dest_name（宛名）, total（金額）, tax_total（内消費税額・任意）,
      remarks（但し書き）, issuer_*（発行元情報）, seal_path, show_issuer_block
    """
    c = canvas.Canvas(save_path, pagesize=A4)
    c.setTitle("領収証")

    x0 = MARGIN_L
    x1 = PAGE_W - MARGIN_R
    y = PAGE_H - 20 * 2.83465

    # ---------------- タイトル ----------------
    draw_bold_centred(c, PAGE_W / 2, y, spaced("領収証"), FONT_NAME, 22)
    y -= 34

    # ---------------- 番号・領収日（右上） ----------------
    if data.get("invoice_number"):
        c.setFont(FONT_MIN, 10)
        c.drawRightString(x1, y, f"No. {data['invoice_number']}")
        y -= 16

    date_str = to_reiwa(data["issue_date"])
    c.setFont(FONT_MIN, 11)
    c.drawRightString(x1, y, date_str)
    y -= 26

    # ---------------- 宛名 ----------------
    c.setFont(FONT_NAME, 16)
    dest_name = data.get("dest_name", "")
    c.drawString(x0, y, dest_name)
    text_w = c.stringWidth(dest_name, FONT_NAME, 16)
    c.drawString(x0 + text_w + 14, y, "様")
    y -= 34

    # ---------------- 金額ボックス ----------------
    total = data.get("total", 0)
    box_h = 46
    box_top = y
    c.setLineWidth(1.1)
    c.rect(x0, box_top - box_h, CONTENT_W, box_h, stroke=1, fill=0)
    c.setFont(FONT_NAME, 12)
    c.drawString(x0 + 12, box_top - 18, "金額")
    amount_str = fmt_yen(total) + "－"
    c.setFont(FONT_NAME, 20)
    c.drawRightString(x0 + CONTENT_W - 14, box_top - 31, amount_str)
    y = box_top - box_h - 16

    # ---------------- 内消費税額 ----------------
    tax_total = data.get("tax_total", 0)
    if tax_total:
        c.setFont(FONT_MIN, 9.5)
        c.drawRightString(x1, y, f"（内消費税等　{fmt_yen(tax_total)}）")
        y -= 20
    else:
        y -= 4

    # ---------------- 但し書き ----------------
    c.setFont(FONT_MIN, 11.5)
    kotogaki = data.get("remarks", "").strip() or "お品代"
    c.drawString(x0, y, f"但し　{kotogaki}として")
    y -= 20
    c.drawString(x0, y, "上記正に領収いたしました。")
    y -= 30

    stamp_bottom = y  # 収入印紙欄・発行元ブロックの開始位置をそろえる

    # ---------------- 収入印紙欄（5万円以上の場合のみ） ----------------
    if total and float(total) >= 50000:
        stamp_w, stamp_h = 75, 95
        stamp_x = x0
        stamp_y = stamp_bottom - stamp_h
        c.setLineWidth(0.6)
        c.rect(stamp_x, stamp_y, stamp_w, stamp_h, stroke=1, fill=0)
        c.setFont(FONT_NAME, 10)
        c.drawCentredString(stamp_x + stamp_w / 2, stamp_y + stamp_h - 18, "収入")
        c.drawCentredString(stamp_x + stamp_w / 2, stamp_y + stamp_h - 34, "印紙")
        c.setFont(FONT_MIN, 8)
        _draw_wrapped_text(
            c,
            "※5万円以上の受取りのため、印紙税法上、収入印紙の貼付・消印が必要です（貼付は発行者にて行ってください）。",
            stamp_x + stamp_w + 12, stamp_bottom - 14,
            CONTENT_W - stamp_w - 12, 11, FONT_MIN, 8,
        )
        y = stamp_y - 26
    else:
        y = stamp_bottom - 10

    # ---------------- 発行元ブロック ----------------
    y = _draw_issuer_block(c, x1, y, data)

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
