# -*- coding: utf-8 -*-
"""
アップデート機能（GitHubで配布したZIPをチェック・適用する）。

■ 開発者（息子さん）向けメモ
  そんなにガチな仕組みではなく、GitHubの「Releases」機能を1つ見に行くだけの
  シンプルな仕組みです（無料機能。Public/Privateどちらでも、料金はかかりません）。
  version.json を手で編集する旧方式より、こちらの方が手間が減ります。

  【最初の1回だけ行う設定】
    1. GitHubに公開リポジトリ（Public repository）を1つ作る
       例：https://github.com/あなたのアカウント/InvoiceGen

    2. invoice_generator.py の中の UPDATE_MANIFEST_URL を、次の形に書き換える：
         https://api.github.com/repos/あなたのアカウント/InvoiceGen/releases/latest
       （これはGitHubが自動的に用意している「最新のRelease情報」を返すURLです。
        あなたが何かファイルを作って置く必要はありません）

  【2回目以降・更新を配布したいとき】
    a. 手元でファイルを修正する
    b. invoice_generator.py の APP_VERSION_NUM を上げる（例："1.1" → "1.2"）
    c. python make_release.py を実行して invoice_generator_tool.zip を作り直す
    d. GitHubのリポジトリページ →「Releases」→「Draft a new release」を開く
    e. 「Choose a tag」で新しいタグを作る（例： v1.2 ← 先頭に v を付ける）
    f. タイトルと、リリースノート（今回の変更点）を書く
    g. 一番下の「Attach binaries」に invoice_generator_tool.zip をドラッグ&ドロップ
    h. 「Publish release」を押す
    i. あとは事務所側で、アプリの「アップデート確認」ボタンを押して
       もらうだけで、最新版が自動的に適用されます。

  ※ version.json を使う旧方式にも一応対応しています（後方互換）。
    UPDATE_MANIFEST_URL が https://api.github.com/... のときはReleases形式、
    それ以外のときは旧来の version.json 形式として読み取ります。
"""
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile

TIMEOUT_CHECK = 10
TIMEOUT_DOWNLOAD = 60

# 更新のときに上書きしない（母が入力した設定・データを守るため）
PRESERVE_NAMES = {"invoice_config.json", "__pycache__", ".git"}


class UpdateError(Exception):
    pass


def parse_version(v):
    """'1.10.2' のようなバージョン文字列を (1, 10, 2) のタプルに変換して比較できるようにする。"""
    parts = []
    for p in str(v).split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def is_configured(manifest_url: str) -> bool:
    if not manifest_url:
        return False
    placeholder_markers = ["USERNAME", "REPO", "あなたのアカウント", "your-username"]
    return not any(m in manifest_url for m in placeholder_markers)


def check_for_update(manifest_url: str) -> dict:
    """更新情報を取得して {version, zip_url, notes} を返す。失敗時は UpdateError を投げる。

    2つの形式に対応している：
      1. GitHubのReleases API（推奨。 https://api.github.com/repos/<user>/<repo>/releases/latest ）
         → タグ名・添付ZIP・リリースノートを自動的に読み取る。version.jsonのメンテナンスが不要になる。
      2. 従来の自前の version.json 形式（{"version", "zip_url", "notes"}）
         → 昔のバージョンとの互換性のために残してある。
    """
    try:
        req = urllib.request.Request(manifest_url, headers={
            "User-Agent": "invoice-tool-updater",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT_CHECK) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        raise UpdateError(f"更新情報の取得に失敗しました：{e}")

    if "tag_name" in data:
        # --- GitHub Releases APIの形式 ---
        version = str(data["tag_name"]).lstrip("vV")
        notes = data.get("body") or ""
        # v1.4から、Releaseには「ソース一式のZIP」以外に、Windows exe用ZIPや
        # Linux用.debも一緒に添付するようになった。この自動更新の仕組みは
        # ソース一式（.pyファイル）を上書きする前提のため、必ず
        # invoice_generator_tool.zip という名前のものだけを対象にする
        # （名前で見つからない場合のみ、後方互換として最初の.zipにフォールバック）。
        assets = data.get("assets", [])
        zip_url = None
        for asset in assets:
            if asset.get("name", "") == "invoice_generator_tool.zip":
                zip_url = asset.get("browser_download_url")
                break
        if not zip_url:
            for asset in assets:
                if asset.get("name", "").lower().endswith(".zip"):
                    zip_url = asset.get("browser_download_url")
                    break
        if not zip_url:
            raise UpdateError("最新のReleaseにZIPファイルが添付されていません")
        return {"version": version, "zip_url": zip_url, "notes": notes}

    # --- 従来の version.json 形式 ---
    if "version" not in data or "zip_url" not in data:
        raise UpdateError("更新情報の内容が正しくありません（version / zip_url が必要です）")
    return data


def download_and_apply_update(zip_url: str, app_dir: str) -> None:
    """ZIPをダウンロードして展開し、app_dir に上書きする。失敗時は UpdateError を投げる。"""
    try:
        with tempfile.TemporaryDirectory(prefix="invoice_update_") as tmp:
            zip_path = os.path.join(tmp, "update.zip")
            req = urllib.request.Request(zip_url, headers={"User-Agent": "invoice-tool-updater"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_DOWNLOAD) as resp, open(zip_path, "wb") as f:
                shutil.copyfileobj(resp, f)

            extract_dir = os.path.join(tmp, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)

            # ZIPの直下が単一フォルダだけの場合は、その中身を本体とみなす
            entries = [e for e in os.listdir(extract_dir) if not e.startswith("__MACOSX")]
            if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
                source_root = os.path.join(extract_dir, entries[0])
            else:
                source_root = extract_dir

            _copy_tree_overwrite(source_root, app_dir)
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError(f"更新の適用に失敗しました：{e}")


def _copy_tree_overwrite(src: str, dst: str) -> None:
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name in PRESERVE_NAMES:
            continue
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            _copy_tree_overwrite(s, d)
        else:
            shutil.copy2(s, d)
