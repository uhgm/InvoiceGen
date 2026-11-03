# -*- coding: utf-8 -*-
"""
請求書かんたん作成ツール（起動用）
===================================
機械操作が苦手な方でも迷わずに請求書PDFを作成できるように、
できるだけ画面をシンプルにし、要所要所に説明文（ヘルプ）を入れています。

■ 使い方（かんたん3ステップ）
  1. 「宛先（請求する相手）」の欄を入力する
  2. 「請求する内容（品目）」の欄を入力する（自動で金額の合計が計算されます）
  3. 画面いちばん下の「📄 請求書PDFを作成」ボタンを押す

分からなくなったら、画面右上の「使い方ヘルプ」ボタンをいつでも押してください。

■ このファイルの役割（開発者向け）
画面は v1.6 から Qt（PySide6）で作っている（main_window.py）。
ところが、v1.5 以前を使っているPCはアプリ内の「アップデート確認」でファイルを
上書きするだけなので、PySide6 が入っていない。そのまま Qt の画面を開こうとすると、
pythonw で起動している場合はエラーも出ずに何も表示されなくなってしまう。
そこでこのファイルは標準ライブラリだけで動くようにしておき、
  1. PySide6 が入っているか確認する
  2. 入っていなければ、Python に標準で付いている Tk で「準備中」の画面を出しながら
     requirements.txt の部品を自動でインストールする
  3. 準備ができたら Qt の画面（main_window.run）を開く
という順番で起動する。起動のしかた（ショートカット・02_start_invoice_tool）は変わらない。
"""
import importlib
import os
import subprocess
import sys
import threading

from app_common import APP_DIR


def _pyside6_available():
    try:
        importlib.invalidate_caches()
        import PySide6.QtWidgets  # noqa: F401
        return True
    except ImportError:
        return False


def _python_for_pip():
    """pip を動かす Python。pythonw.exe（画面なし起動）で動いているときは、
    同じフォルダの python.exe を使う。"""
    exe = sys.executable
    if sys.platform.startswith("win") and os.path.basename(exe).lower() == "pythonw.exe":
        console_exe = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(console_exe):
            return console_exe
    return exe


def _run_pip_install():
    """requirements.txt の部品をインストールする。(成功したか, 出力の最後の部分) を返す。"""
    cmd = [_python_for_pip(), "-m", "pip", "install", "-r", os.path.join(APP_DIR, "requirements.txt")]
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW（黒い画面を出さない）
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", **kwargs)
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-1500:]
    except Exception as e:
        return False, str(e)


def _setup_command_hint():
    if sys.platform.startswith("win"):
        return "このツールのフォルダにある「01_setup.bat」をダブルクリックしてから、もう一度開いてください。"
    return "このツールのフォルダで「bash 01_setup.sh」を実行してから、もう一度開いてください。"


def _install_with_progress_window():
    """「準備中」の画面を出しながら部品をインストールする。成功したら True。"""
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception:
        # Tk も使えない環境では、画面を出さずにインストールだけ試す
        ok, log = _run_pip_install()
        if not ok:
            print("必要な部品のインストールに失敗しました。\n" + _setup_command_hint() + "\n\n" + log,
                  file=sys.stderr)
        return ok

    root = tk.Tk()
    root.title("請求書かんたん作成ツール - 準備中")
    root.geometry("520x170")
    root.resizable(False, False)
    tk.Label(
        root,
        text="新しい画面の部品を準備しています。\n"
             "数分かかることがあります。インターネットにつないだまま、\n"
             "この画面が閉じるまでお待ちください（最初の1回だけです）。",
        justify="left", padx=20, pady=16,
    ).pack(anchor="w")
    bar = ttk.Progressbar(root, mode="indeterminate", length=460)
    bar.pack(padx=20)
    bar.start(12)

    result = {}

    def _worker():
        result["ok"], result["log"] = _run_pip_install()

    def _wait():
        if "ok" in result:
            root.destroy()
        else:
            root.after(300, _wait)

    threading.Thread(target=_worker, daemon=True).start()
    root.after(300, _wait)
    root.mainloop()

    if not result.get("ok"):
        err_root = tk.Tk()
        err_root.withdraw()
        messagebox.showerror(
            "準備できませんでした",
            "画面の部品のインストールに失敗しました。\n"
            "インターネットに接続されているかご確認ください。\n\n"
            + _setup_command_hint() + "\n\n（技術情報）\n" + result.get("log", "")[-600:],
        )
        err_root.destroy()
        return False
    return True


def main():
    # exe/deb 版は PySide6 を同梱しているので、確認やインストールは不要
    if not getattr(sys, "frozen", False) and not _pyside6_available():
        if not _install_with_progress_window() or not _pyside6_available():
            return 1
    from main_window import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
