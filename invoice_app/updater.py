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

    2. app_common.py の中の UPDATE_MANIFEST_URL を、次の形に書き換える：
         https://api.github.com/repos/あなたのアカウント/InvoiceGen/releases/latest
       （これはGitHubが自動的に用意している「最新のRelease情報」を返すURLです。
        あなたが何かファイルを作って置く必要はありません）

  【2回目以降・更新を配布したいとき】
    a. 手元でファイルを修正する
    b. app_common.py の APP_VERSION_NUM を上げる（例："1.1" → "1.2"）
    c. python make_release.py を実行して invoice_generator_tool.zip を作り直す
    d. GitHubのリポジトリページ →「Releases」→「Draft a new release」を開く
    e. 「Choose a tag」で新しいタグを作る（例： v1.2 ← 先頭に v を付ける）
    f. タイトルと、リリースノート（今回の変更点）を書く
    g. 一番下の「Attach binaries」に invoice_generator_tool.zip をドラッグ&ドロップ
    h. 「Publish release」を押す
    i. あとは事務所側で、アプリの「アップデート確認」ボタンを押して
       もらうだけで、最新版が自動的に適用されます。

  ※ Windows版（インストーラーで入れたexe）は .py を上書きできないので、
    Releaseに添付された invoice-generator-tool-windows-setup.exe を
    ダウンロード・確認してから、画面の質問なしで上書きインストールします
    （download_installer / launch_installer）。このインストーラーは
    Releaseを公開すると GitHub Actions が自動で作って添付します（手で添付は不要）。

  ※ version.json を使う旧方式にも一応対応しています（後方互換）。
    UPDATE_MANIFEST_URL が https://api.github.com/... のときはReleases形式、
    それ以外のときは旧来の version.json 形式として読み取ります。
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

TIMEOUT_CHECK = 10
TIMEOUT_DOWNLOAD = 60

# ------------------------------------------------------------------
# Windows版（インストーラーで入れたexe）の更新
# ------------------------------------------------------------------
# exe版は .py ファイルを上書きする仕組みが使えないので、Releaseに添付された
# インストーラー（setup.exe）をダウンロードして、画面の質問なしで上書きインストールする。
# この名前は installer.iss の OutputBaseFilename と、
# .github/workflows/build-windows-exe.yml の INSTALLER と必ず同じにすること。
WINDOWS_INSTALLER_NAME = "invoice-generator-tool-windows-setup.exe"

# インストーラー（Inno Setup）に渡す引数。
#   /SILENT              … 質問の画面は出さず、進み具合の画面だけ出す
#   /SUPPRESSMSGBOXES    … 確認のメッセージを出さない
#   /NORESTART           … パソコンの再起動はしない
#   /CLOSEAPPLICATIONS   … このツールがまだ開いていたら閉じてから上書きする
# インストールが終わると、installer.iss の [Run] でツールが自動で開き直す。
INSTALLER_ARGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]

# ダウンロードしたインストーラーを置く一時フォルダの名前の頭
_INSTALLER_TMP_PREFIX = "invoice_setup_"

# 更新のときに上書きしない（母が入力した設定・データを守るため）
PRESERVE_NAMES = {"invoice_config.json", "__pycache__", ".git"}


class UpdateError(Exception):
    pass


class UpdateCancelled(UpdateError):
    """ダウンロード中に「やめる」が押されたとき。"""


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
    """更新情報を取得して {version, zip_url, notes, ...} を返す。失敗時は UpdateError を投げる。

    GitHubのReleases形式のときは、次も入れて返す（無いときは None）：
      installer_url / installer_size / installer_sha256 … Windows版インストーラー
      page_url … そのReleaseのページ（ブラウザで開く用）

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
        installer = _find_installer_asset(assets)
        if not zip_url and not installer:
            raise UpdateError("最新のReleaseにZIPファイルが添付されていません")
        return {
            "version": version,
            "zip_url": zip_url,
            "notes": notes,
            "installer_url": installer.get("browser_download_url") if installer else None,
            "installer_size": installer.get("size") if installer else None,
            "installer_sha256": _sha256_from_digest(installer.get("digest")) if installer else None,
            "page_url": data.get("html_url"),
        }

    # --- 従来の version.json 形式 ---
    if "version" not in data or "zip_url" not in data:
        raise UpdateError("更新情報の内容が正しくありません（version / zip_url が必要です）")
    return data


def _find_installer_asset(assets):
    """Releaseの添付ファイルから、Windows版インストーラーを名前で探す（完全一致のみ）。"""
    for asset in assets:
        if asset.get("name", "") == WINDOWS_INSTALLER_NAME and asset.get("browser_download_url"):
            return asset
    return None


def _sha256_from_digest(digest):
    """GitHubが添付ファイルごとに付けている "sha256:<16進>" から、16進の部分を取り出す。"""
    if isinstance(digest, str) and digest.lower().startswith("sha256:"):
        value = digest.split(":", 1)[1].strip().lower()
        if len(value) == 64:
            return value
    return None


def can_self_install() -> bool:
    """インストーラーでの自動更新が使える版か（＝WindowsのPyInstaller版か）。"""
    return sys.platform.startswith("win") and bool(getattr(sys, "frozen", False))


def _cleanup_old_installers():
    """前回の更新でダウンロードしたインストーラーを消す（1つ100MB前後あるため）。
    前回のインストールはとっくに終わっているので、消してしまってよい。"""
    pattern = os.path.join(tempfile.gettempdir(), _INSTALLER_TMP_PREFIX + "*")
    for path in glob.glob(pattern):
        shutil.rmtree(path, ignore_errors=True)


def download_installer(url, expected_size=None, expected_sha256=None, progress=None):
    """インストーラーをダウンロードして、壊れていないか確かめてから、そのパスを返す。

    progress(済んだバイト数, 全体のバイト数) を何度も呼ぶ（全体が分からないときは 0）。
    progress が False を返したら中止して UpdateCancelled を投げる。
    大きさ・SHA-256（GitHubが付けている値）が合わないときは UpdateError を投げる。
    """
    _cleanup_old_installers()
    tmp = tempfile.mkdtemp(prefix=_INSTALLER_TMP_PREFIX)
    path = os.path.join(tmp, WINDOWS_INSTALLER_NAME)
    part = path + ".part"
    sha = hashlib.sha256()
    done = 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "invoice-tool-updater"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_DOWNLOAD) as resp, open(part, "wb") as f:
            total = expected_size or int(resp.headers.get("Content-Length") or 0)
            if progress and progress(0, total) is False:
                raise UpdateCancelled("ダウンロードを中止しました")
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if progress and progress(done, total) is False:
                    raise UpdateCancelled("ダウンロードを中止しました")

        if expected_size and done != expected_size:
            raise UpdateError(
                f"ダウンロードしたファイルの大きさが違います（{done} / {expected_size} バイト）。"
                "通信が途中で切れた可能性があります")
        if expected_sha256 and sha.hexdigest() != expected_sha256.lower():
            raise UpdateError("ダウンロードしたファイルが壊れています（SHA-256が一致しません）")
        with open(part, "rb") as f:
            if f.read(2) != b"MZ":
                raise UpdateError("ダウンロードしたファイルがWindowsのプログラムではありません")
        os.replace(part, path)
        return path
    except UpdateError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise UpdateError(f"インストーラーのダウンロードに失敗しました：{e}")


def launch_installer(installer_path):
    """インストーラーを、このツールとは切り離して起動する（このあとツールは自分で終了する）。

    インストールの記録（ログ）は、インストーラーと同じフォルダの install.log に残る。
    起動できなかったときは UpdateError を投げる。
    """
    log_path = os.path.join(os.path.dirname(installer_path), "install.log")
    args = INSTALLER_ARGS + [f"/LOG={log_path}"]
    flags = 0
    if sys.platform.startswith("win"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            [installer_path] + args,
            creationflags=flags, close_fds=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return log_path
    except OSError as e:
        # 管理者の許可が必要なインストーラーだった場合（ERROR_ELEVATION_REQUIRED）は、
        # Windowsの「許可しますか？」の画面を出して起動し直す。
        if getattr(e, "winerror", None) == 740 and hasattr(os, "startfile"):
            try:
                os.startfile(installer_path, "runas", subprocess.list2cmdline(args))
                return log_path
            except OSError as e2:
                raise UpdateError(f"インストーラーを起動できませんでした：{e2}")
        raise UpdateError(f"インストーラーを起動できませんでした：{e}")


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
