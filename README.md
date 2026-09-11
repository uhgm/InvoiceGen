# InvoiceGen（請求書かんたん作成ツール）

Windows 11で動く、請求書PDF作成デスクトップアプリです。
機械操作が苦手な方でも迷わず使えるように、UIをシンプルにし、
画面のあちこちに説明（ヘルプ）を入れてあります。WebUIは使いません。

> A simple Windows desktop app (Tkinter + ReportLab) that generates
> Japanese-style invoice PDFs, built for a non-technical end user.
> Not intended as a general-purpose OSS project — shared here mainly
> as a private update channel (see "アップデートの仕組み" below).

現在のバージョン：**v1.1**


## できること

- 宛先・請求元・品目（数量×単価で金額自動計算）・消費税・備考・振込先（複数行）を画面から入力してPDF化
- 請求元プロファイル（郵便番号込み住所／事務所名／代表者名／電話番号）を右上にまとめて印字、事務所名に会社印を重ねて印字
- 請求元プロファイルの印字有無をチェックボックスで切り替え可能
- 会社印の画像や振込先などの設定は自動で記憶され、次回以降入力し直す不要
- 画面右上の「？使い方ヘルプ」ボタンと各入力欄のツールチップで操作をサポート
- 画面右上の「🔄 アップデート確認」ボタンで、このリポジトリから最新版を取得・適用
- 入力データ（`invoice_config.json`）はアプリのフォルダとは別の場所
  （`%APPDATA%\InvoiceGeneratorTool\`）に保存されるため、
  このリポジトリに個人情報が混ざる事故を防いでいます


## フォルダ構成

```
InvoiceGen/
├─ version.json                  ← アプリが更新確認時に読みに来るファイル（必須）
├─ invoice_generator_tool.zip    ← 配布用ZIP。アプリが自動ダウンロードする実体（必須）
├─ invoice_generator.py          ← アプリ本体（GUI）
├─ pdf_builder.py                ← 請求書PDFの描画処理
├─ updater.py                    ← アップデート機能の実装
├─ make_release.py               ← 配布用ZIPを安全に作るスクリプト（開発者用）
├─ requirements.txt              ← 必要なPythonパッケージ（reportlab）
├─ 01_setup.bat                  ← 初回セットアップ（Windows用）
├─ 02_start_invoice_tool.bat     ← アプリ起動用（Windows用）
├─ create_shortcut.vbs           ← デスクトップショートカット作成用
├─ assets/                       ← 埋め込みフォント（IPAフォント）等
├─ setup_guide.txt               ← エンドユーザー（母）向けセットアップ手順
├─ DEVELOPER_NOTES.txt           ← 開発者向けメモ（アップデート機能の仕組み）
└─ RELEASE_WORKFLOW.txt          ← 開発者向け：更新を配布する手順のチェックリスト
```


## エンドユーザー向けセットアップ

Windows 11のPCで使う場合は、`invoice_generator_tool.zip` を展開して
`setup_guide.txt` の手順に沿って進めてください（Pythonのインストール →
`01_setup.bat` を実行 → デスクトップにできたアイコンから起動、という流れです）。


## 開発者向け：アップデートの仕組み

このリポジトリは**Public**です。母のPC上のアプリが、起動時ではなく
「🔄 アップデート確認」ボタンを押したタイミングで、このリポジトリ直下の

- `version.json`（バージョン番号とZIPのURLが書かれたJSON）
- `invoice_generator_tool.zip`（アプリ本体一式）

を確認しに行き、新しいバージョンがあればダウンロード・上書きします。
署名検証やロールバックなどは実装していない、素朴な仕組みです
（このリポジトリへの書き込み権限を持つのは自分だけ、という前提で運用してください）。

**個人情報の混入対策**：母が入力する請求書の内容（振込先・会社情報など）は
`invoice_config.json` に保存されますが、これはアプリのフォルダの外
（Windowsの個人設定用フォルダ）に保存される設計になっており、
このリポジトリやZIPに混ざることはありません。また `make_release.py` は
配布してよいファイルだけを明示的に選んでZIPを作るので、手元にテスト用の
PDFや設定ファイルが残っていても配布ZIPには含まれません。

新しいバージョンを配布する具体的な手順は **[RELEASE_WORKFLOW.txt](./RELEASE_WORKFLOW.txt)**
にチェックリスト形式でまとめてあります。仕組みの詳細（初回セットアップの
やり方など）は **[updater.py](./updater.py)** 冒頭のコメントと
**[DEVELOPER_NOTES.txt](./DEVELOPER_NOTES.txt)** を参照してください。

概要だけ書くと：

1. コードを直す
2. `invoice_generator.py` の `APP_VERSION_NUM` を上げる
3. `python make_release.py` を実行して配布用ZIPを作り直す
4. `version.json` の `version` と `notes` を更新する
5. `version.json` と新しい `invoice_generator_tool.zip` をこのリポジトリに上書きコミットする


## 使用技術

- Python 3 / Tkinter（GUI）
- [ReportLab](https://www.reportlab.com/)（PDF生成）
- フォントは [IPAフォント](https://moji.or.jp/ipafont/)（IPAフォントライセンスv1.0）を同梱・埋め込み
  （ライセンス全文は `assets/IPA_Font_License.txt`）


## クレジット

- 開発：ClaudeCord & 井上
