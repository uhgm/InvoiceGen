# -*- coding: utf-8 -*-
"""Windows版の自動更新を、アプリの「🔄 アップデート確認」と同じ関数（updater.py）で試す。
GitHub Actions（build-windows-exe.yml）から使う。

  python test_windows_update.py --installer dist/<setup.exe> --launch --log-out update_log.txt
      手元に「偽の最新Release（v99.0）」を用意して、
        更新情報の取得 → ダウンロード（大きさ・SHA-256の確認）→ インストーラーの起動
      まで行う。わざと壊したファイル・中止のときに、ちゃんと止まることも確かめる。
      起動したインストーラーのログの場所を --log-out のファイルに書く。

  python test_windows_update.py --installer dist/<setup.exe> --release-api-url <URL>
      GitHubに添付した本物のReleaseの情報で、取得 → ダウンロード・確認まで行い、
      ダウンロードしたものが --installer のファイルと同じかを確かめる（起動はしない）。
"""
import argparse
import hashlib
import http.server
import json
import os
import sys
import threading
import urllib.request

# 英語版Windowsでは画面出力が cp1252 になり、日本語を出せないので UTF-8 にする
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "invoice_app")))
import updater  # noqa: E402


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Server:
    """更新情報（JSON）とファイルを返す、テスト用の小さなWebサーバー。"""

    def __init__(self, files):
        self.files = files  # {"/path": bytes または ファイルのパス}
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = outer.files.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                if isinstance(body, str):
                    with open(body, "rb") as f:
                        body = f.read()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # 「やめる」のテストで、途中で切られたとき

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


def expect_error(name, func, error_type=updater.UpdateError):
    try:
        func()
    except error_type as e:
        print(f"OK: {name} → 止まった（{e}）")
        return
    raise AssertionError(f"{name} のとき、止まるはずなのに止まらなかった")


def test_fake_release(installer, launch, log_out):
    size = os.path.getsize(installer)
    sha = sha256_of(installer)
    server = Server({"/download/setup.exe": installer})
    name = updater.WINDOWS_INSTALLER_NAME
    release = {
        "tag_name": "v99.0",
        "body": "テスト用の更新",
        "html_url": server.base + "/release-page",
        "assets": [
            # 名前の順でインストーラーより前に来るファイル（取り違えないかの確認）
            {"name": "invoice-generator-tool-windows-x64.zip",
             "browser_download_url": server.base + "/download/wrong.zip", "size": 1},
            {"name": name, "browser_download_url": server.base + "/download/setup.exe",
             "size": size, "digest": "sha256:" + sha},
            {"name": "invoice_generator_tool.zip",
             "browser_download_url": server.base + "/download/source.zip", "size": 1},
        ],
    }
    server.files["/release.json"] = json.dumps(release).encode("utf-8")

    info = updater.check_for_update(server.base + "/release.json")
    assert info["version"] == "99.0", info
    assert info["installer_url"] == server.base + "/download/setup.exe", info
    assert info["installer_size"] == size, info
    assert info["installer_sha256"] == sha, info
    assert info["zip_url"] == server.base + "/download/source.zip", info
    assert info["page_url"] == server.base + "/release-page", info
    print("OK: 更新情報からインストーラーを正しく選んだ")

    url = info["installer_url"]
    expect_error("SHA-256が違う", lambda: updater.download_installer(url, size, "0" * 64))
    expect_error("大きさが違う", lambda: updater.download_installer(url, size + 1, sha))
    expect_error("「やめる」を押した",
                 lambda: updater.download_installer(url, size, sha, lambda d, t: d == 0),
                 updater.UpdateCancelled)
    expect_error("Windowsのプログラムではない",
                 lambda: updater.download_installer(server.base + "/release.json"))

    calls = []
    path = updater.download_installer(url, size, sha, lambda d, t: calls.append((d, t)))
    assert os.path.basename(path) == name, path
    assert sha256_of(path) == sha, "ダウンロードしたファイルの中身が違う"
    assert calls and calls[-1] == (size, size), calls[-3:]
    print(f"OK: ダウンロードと確認ができた（進み具合の表示 {len(calls)} 回）: {path}")
    server.close()

    if launch:
        log_path = updater.launch_installer(path)
        print(f"OK: インストーラーを起動した（ログ: {log_path}）")
        with open(log_out, "w", encoding="utf-8") as f:
            f.write(log_path)


def test_real_release(installer, api_url):
    """GitHubに添付したものを、アプリと同じ手順で取得・確認する。"""
    headers = {"User-Agent": "invoice-tool-ci", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(api_url, headers=headers), timeout=30) as r:
        raw = r.read()
    server = Server({"/release.json": raw})  # アプリは認証なしで読むので、同じ中身を手元から返す
    info = updater.check_for_update(server.base + "/release.json")
    server.close()

    size = os.path.getsize(installer)
    sha = sha256_of(installer)
    assert info["installer_url"], "Releaseにインストーラーが添付されていない"
    assert info["installer_size"] == size, (info["installer_size"], size)
    if info["installer_sha256"]:
        assert info["installer_sha256"] == sha, "GitHubのSHA-256と、作ったファイルが違う"
    else:
        print("注意: GitHubがSHA-256（digest）を返さなかったので、大きさだけで確かめる")
    path = updater.download_installer(info["installer_url"], info["installer_size"],
                                      info["installer_sha256"])
    assert sha256_of(path) == sha, "ダウンロードしたものが、作ったファイルと違う"
    print(f"OK: Releaseのインストーラーを、アプリと同じ手順でダウンロード・確認できた（{size} バイト）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--installer", required=True)
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--log-out", default="update_log.txt")
    ap.add_argument("--release-api-url")
    args = ap.parse_args()
    if args.release_api_url:
        test_real_release(args.installer, args.release_api_url)
    else:
        test_fake_release(args.installer, args.launch, args.log_out)


if __name__ == "__main__":
    main()
