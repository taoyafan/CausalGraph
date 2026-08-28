"""下载并归档数据源原件到本地，记录 URL / 抓取时间 / 校验和。

用法:
  python -m cgraph.archive <url> [文件名]

返回并打印可直接填入数据源 JSON 头部的出处字段：
  local_copy / retrieved_at / sha256 / bytes
只依赖标准库 urllib，不引第三方。
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_DIR = os.path.join(REPO_ROOT, "data", "sources", "raw")


def archive_url(url, dest_dir=RAW_DIR, filename=None, timeout=30):
    """下载 url 到 dest_dir，返回出处元数据 dict。"""
    os.makedirs(dest_dir, exist_ok=True)
    req = Request(url, headers={"User-Agent": "cgraph-archiver"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (仅归档已知来源)
        data = resp.read()

    if not filename:
        filename = os.path.basename(url.split("?")[0]) or "source.bin"
    path = os.path.join(dest_dir, filename)
    with open(path, "wb") as f:
        f.write(data)

    return {
        "source_url": url,
        "local_copy": os.path.relpath(path, REPO_ROOT).replace("\\", "/"),
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m cgraph.archive <url> [文件名]", file=sys.stderr)
        sys.exit(1)
    name = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(archive_url(sys.argv[1], filename=name), ensure_ascii=False, indent=2))
