#!/usr/bin/env bash
# 請求書かんたん作成ツール - 起動用（Linux用）
cd "$(dirname "$0")" || exit 1

if [ -x ".venv/bin/python" ]; then
    exec .venv/bin/python invoice_generator.py
fi

echo
echo "[エラー] セットアップがまだ完了していません。"
echo "先にこのフォルダで次を実行してください： bash 01_setup.sh"
echo
read -r -p "Enterキーを押すと終了します..." _
