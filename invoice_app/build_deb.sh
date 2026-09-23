#!/usr/bin/env bash
# .debパッケージを作るスクリプト（開発者専用。母上は使いません）。
#
# 何をしているか：
#   1. PyInstallerで、Pythonが入っていないパソコンでも動く単体アプリ
#      （実行ファイル一式）を作る（--onedir形式。中身は "_internal" フォルダに入る）
#   2. それを /opt/invoice-generator-tool/ に置く形の.debパッケージに詰める
#      （/usr/bin にランチャー、/usr/share/applications にアプリ一覧用の
#       ショートカットを置く、Debian/Ubuntu系の標準的な作り方）
#
# 使い方：
#     bash build_deb.sh
# 実行すると、このフォルダに invoice-generator-tool_<バージョン>_amd64.deb ができる。
#
# 前提：
#   - Ubuntu/Debian系のLinux（dpkg-deb コマンドが必要）
#   - python3-venv, python3-tk が入っていること
#     （無ければ： sudo apt install python3-venv python3-tk）
set -e
cd "$(dirname "$0")"

PKG_NAME="invoice-generator-tool"
ARCH="amd64"
BUILD_VENV=".build-venv"

APP_VERSION="$(python3 -c "
import re
src = open('invoice_generator.py', encoding='utf-8').read()
print(re.search(r'APP_VERSION_NUM = \"([^\"]+)\"', src).group(1))
")"
SUPPORT_EMAIL="$(python3 -c "
import re
src = open('invoice_generator.py', encoding='utf-8').read()
print(re.search(r'APP_SUPPORT_EMAIL = \"([^\"]+)\"', src).group(1))
")"

DIST_NAME="${PKG_NAME}_${APP_VERSION}_${ARCH}"

echo "============================================="
echo "  .deb ビルド： ${PKG_NAME} v${APP_VERSION} (${ARCH})"
echo "============================================="
echo

if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "[エラー] dpkg-deb が見つかりません。Debian/Ubuntu系のLinuxで実行してください。"
    exit 1
fi

echo "[1/3] ビルド専用の仮想環境を用意しています（${BUILD_VENV}）..."
if [ ! -d "$BUILD_VENV" ]; then
    python3 -m venv --system-site-packages "$BUILD_VENV"
fi
"$BUILD_VENV/bin/python" -m pip install --upgrade pip >/dev/null 2>&1
"$BUILD_VENV/bin/pip" install -r requirements.txt pyinstaller >/dev/null

echo "[2/3] PyInstallerで実行ファイル一式を作成しています..."
rm -rf build dist "${PKG_NAME}.spec" "$DIST_NAME" "${DIST_NAME}.deb"
"$BUILD_VENV/bin/pyinstaller" --name "$PKG_NAME" --onedir --windowed \
    --add-data "assets:assets" \
    invoice_generator.py

echo "[3/3] .debパッケージに詰めています..."
PKG_ROOT="$DIST_NAME"
INSTALL_DIR="$PKG_ROOT/opt/$PKG_NAME"
mkdir -p "$INSTALL_DIR"
cp -r "dist/$PKG_NAME/." "$INSTALL_DIR/"

mkdir -p "$PKG_ROOT/usr/bin"
cat > "$PKG_ROOT/usr/bin/$PKG_NAME" <<EOF
#!/bin/sh
exec "/opt/$PKG_NAME/$PKG_NAME" "\$@"
EOF
chmod +x "$PKG_ROOT/usr/bin/$PKG_NAME"

mkdir -p "$PKG_ROOT/usr/share/applications"
cat > "$PKG_ROOT/usr/share/applications/$PKG_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=請求書かんたん作成ツール
Comment=請求書・領収証のPDFをかんたんに作成するツール
Exec=/usr/bin/$PKG_NAME
Icon=x-office-document
Terminal=false
Categories=Office;
EOF

DEB_SIZE_KB=$(du -sk "$INSTALL_DIR" | cut -f1)
mkdir -p "$PKG_ROOT/DEBIAN"
cat > "$PKG_ROOT/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $APP_VERSION
Section: office
Priority: optional
Architecture: $ARCH
Installed-Size: $DEB_SIZE_KB
Maintainer: InvoiceGeneratorTool <$SUPPORT_EMAIL>
Description: 請求書かんたん作成ツール
 請求書・領収証のPDFをかんたんに作成するデスクトップアプリです。
 Pythonのインストール不要で、単体で動作します。
EOF

dpkg-deb --root-owner-group --build "$PKG_ROOT" "${DIST_NAME}.deb"
rm -rf "$PKG_ROOT"

echo
echo "完成： ${DIST_NAME}.deb"
echo "インストール確認： sudo apt install ./${DIST_NAME}.deb"
