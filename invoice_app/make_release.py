# -*- coding: utf-8 -*-
"""
リリース用ZIPを作るスクリプト（開発者専用。母上は使いません）。

★なぜこのスクリプトがあるか★
このフォルダをまるごとZIP化すると、もし手元でテストした際にできた
invoice_config.json（振込先などの個人情報）や、生成した請求書PDFが
まぎれ込んでいた場合、それごとGitHubにアップロードしてしまう事故が
起こり得ます。

このスクリプトは「配布してよいと分かっているファイルだけ」を
明示的に選んでZIPに入れるので、そうした事故を防げます。
（invoice_config.jsonは今のバージョンではこのフォルダの外
　　＝ %APPDATA%\\InvoiceGeneratorTool\\ に保存されるようになったので
　　二重の安全策になっています）

使い方：
    python make_release.py

実行すると、このフォルダの中に invoice_generator_tool.zip が
作られます。これをGitHubリポジトリの直下にアップロードしてください。
"""
import os
import zipfile

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_ZIP = os.path.join(THIS_DIR, "invoice_generator_tool.zip")

# ZIPの中を1枚のフォルダで包む（母上が手動で解凍したときに、
# ファイルが散らからずこのフォルダの中にまとまるようにするため）。
# アップデート機能側（updater.py）は、包んでいても包んでいなくても
# 自動で判定できるようになっている。
ZIP_ROOT_FOLDER = "InvoiceGeneratorTool"

# 配布してよいファイル・フォルダだけを明示的に列挙する（ホワイトリスト方式）
INCLUDE_FILES = [
    "invoice_generator.py",
    "pdf_builder.py",
    "updater.py",
    "requirements.txt",
    "01_setup.bat",
    "02_start_invoice_tool.bat",
    "create_shortcut.vbs",
    "setup_guide.txt",
]
INCLUDE_DIRS = [
    "assets",
]

# 万一まぎれ込んでいても絶対に含めないファイル名・拡張子
NEVER_INCLUDE_NAMES = {"invoice_config.json"}
NEVER_INCLUDE_EXTS = {".pdf"}


def _is_safe(path, name):
    if name in NEVER_INCLUDE_NAMES:
        print(f"  [スキップ] {path}（個人情報が入りうるファイルのため除外）")
        return False
    ext = os.path.splitext(name)[1].lower()
    if ext in NEVER_INCLUDE_EXTS:
        print(f"  [スキップ] {path}（PDFファイルのため除外）")
        return False
    return True


def build_release_zip():
    if os.path.exists(OUTPUT_ZIP):
        os.remove(OUTPUT_ZIP)

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in INCLUDE_FILES:
            fpath = os.path.join(THIS_DIR, fname)
            if not os.path.exists(fpath):
                print(f"  [注意] {fname} が見つかりません。スキップします。")
                continue
            if _is_safe(fname, fname):
                arcname = f"{ZIP_ROOT_FOLDER}/{fname}"
                zf.write(fpath, arcname=arcname)
                print(f"  追加: {arcname}")

        for dname in INCLUDE_DIRS:
            dpath = os.path.join(THIS_DIR, dname)
            if not os.path.isdir(dpath):
                continue
            for root, dirs, files in os.walk(dpath):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, THIS_DIR)
                    if _is_safe(rel, f):
                        arcname = f"{ZIP_ROOT_FOLDER}/{rel}"
                        zf.write(full, arcname=arcname)
                        print(f"  追加: {arcname}")

    print()
    print(f"完成: {OUTPUT_ZIP}")
    print("このZIPを GitHubリポジトリの直下にアップロードしてください。")


if __name__ == "__main__":
    print("リリース用ZIPを作成しています...")
    build_release_zip()
