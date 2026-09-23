#!/usr/bin/env bash
# デスクトップ・アプリ一覧にショートカット（.desktop）を作る
# （Windows版の create_shortcut.vbs のLinux版。01_setup.sh から呼ばれる）
APP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
START_SCRIPT="$APP_DIR/02_start_invoice_tool.sh"

DESKTOP_ENTRY="[Desktop Entry]
Type=Application
Name=請求書かんたん作成ツール
Comment=請求書・領収証のPDFをかんたんに作成するツール
Exec=bash \"$START_SCRIPT\"
Path=$APP_DIR
Terminal=false
Icon=x-office-document
Categories=Office;
"

write_entry() {
    local dest="$1"
    mkdir -p "$(dirname "$dest")"
    printf '%s' "$DESKTOP_ENTRY" > "$dest"
    chmod +x "$dest"
    # GNOME系では「信頼済み」にしないとダブルクリックで警告が出るため、
    # 対応していれば設定しておく（失敗しても無視して問題ない）。
    command -v gio >/dev/null 2>&1 && gio set "$dest" metadata::trusted true >/dev/null 2>&1
}

if [ -d "$HOME/Desktop" ]; then
    write_entry "$HOME/Desktop/InvoiceGeneratorTool.desktop"
fi
write_entry "$HOME/.local/share/applications/invoice-generator-tool.desktop"

echo "ショートカットを作成しました。"
