#!/usr/bin/env bash
# 請求書かんたん作成ツール - 初回セットアップ（Linux用）
#
# 使い方：ターミナルでこのフォルダに移動して次を実行してください。
#     bash 01_setup.sh
cd "$(dirname "$0")" || exit 1

echo "============================================="
echo "  請求書かんたん作成ツール - 初回セットアップ"
echo "============================================="
echo

PYCMD=""
if command -v python3 >/dev/null 2>&1; then
    PYCMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYCMD="python"
else
    echo "[エラー] Python が見つかりませんでした。"
    echo "お使いのディストリビューションのパッケージ管理ツールで"
    echo "Python3 をインストールしてから、もう一度実行してください。"
    echo "  例（Ubuntu/Debian系）： sudo apt install python3 python3-venv python3-tk"
    exit 1
fi
echo "Python (${PYCMD}) が見つかりました。"

# tkinter（画面表示に必要なライブラリ）が入っているか確認する。
# これはpipではインストールできず、OS側のパッケージとして必要なため、
# 無ければここで案内して終了する（sudoが必要な操作は自動実行しない）。
if ! "$PYCMD" -c "import tkinter" >/dev/null 2>&1; then
    echo
    echo "[エラー] 画面表示に必要な 'tkinter' が見つかりませんでした。"
    echo "以下のいずれかを実行してから、もう一度 01_setup.sh を実行してください。"
    echo "  Ubuntu/Debian系： sudo apt install python3-tk"
    echo "  Fedora系：       sudo dnf install python3-tkinter"
    echo "  Arch系：         sudo pacman -S tk"
    exit 1
fi
echo "tkinter（画面表示ライブラリ）も見つかりました。"
echo

echo "必要なファイルをインストールしています（少し時間がかかります）..."
# 既存のtkinter（OS側のライブラリ）を引き継ぐため --system-site-packages を付ける。
"$PYCMD" -m venv --system-site-packages .venv
if [ $? -ne 0 ]; then
    echo "[エラー] 仮想環境の作成に失敗しました。"
    echo "  Ubuntu/Debian系では 'sudo apt install python3-venv' が必要な場合があります。"
    exit 1
fi

.venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1
.venv/bin/pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo
    echo "[エラー] 必要なファイルのインストール中に問題が発生しました。"
    echo "インターネット接続を確認してから、もう一度 01_setup.sh を実行してください。"
    exit 1
fi

echo
echo "デスクトップ・アプリ一覧にショートカットを作成しています..."
bash "$(dirname "$0")/create_shortcut.sh" "$(cd "$(dirname "$0")" && pwd)" || true

echo
echo "============================================="
echo "  セットアップ完了！"
echo "============================================="
echo
echo "デスクトップ（またはアプリ一覧）に「請求書かんたん作成ツール」の"
echo "アイコンが追加されました。次からはそちらから起動できます。"
echo "（見つからない場合は、このフォルダで次を実行してください： bash 02_start_invoice_tool.sh）"
echo
read -r -p "Enterキーを押すと終了します..." _
