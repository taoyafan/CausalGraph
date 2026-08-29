"""本地网页服务(stdlib only): 起一个 http.server 展示因果图。

路由:
  GET /                 -> web/index.html(单页应用)
  GET /web/*            -> web/ 下静态资源
  GET /api/nodes        -> 可 focus 的节点列表
  GET /api/focus?node=  -> 以该节点为根、求值后的贡献树 JSON
  GET /api/drilldown?node= -> 公式钻取卡片 JSON(公式头+结果+输入插槽, 只渲染一层)

前端与后端只通过 /api/* JSON 通信,便于日后把同一份 API 接到微信小程序。
"""

import json
import os
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .loader import load_world
from .webexport import build_drilldown, build_focus, list_focusable

WEB_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "web"))
_CT = {".html": "text/html", ".js": "application/javascript",
       ".css": "text/css", ".json": "application/json"}


def _make_handler(sources_dir, operators_dir, samples, seed):
    def load():
        random.seed(seed)
        return load_world(sources_dir, operators_dir, samples)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # 静默,避免刷屏

        def _send(self, code, body, ctype):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False), "application/json")

        def _static(self, rel):
            path = os.path.normpath(os.path.join(WEB_DIR, rel))
            if not path.startswith(WEB_DIR) or not os.path.isfile(path):
                self._send(404, "not found", "text/plain")
                return
            ext = os.path.splitext(path)[1]
            with open(path, "rb") as f:
                self._send(200, f.read(), _CT.get(ext, "application/octet-stream"))

        def do_GET(self):
            u = urlparse(self.path)
            try:
                if u.path in ("/", "/index.html"):
                    self._static("index.html")
                elif u.path.startswith("/web/"):
                    self._static(u.path[len("/web/"):])
                elif u.path == "/api/nodes":
                    self._json(list_focusable(load()))
                elif u.path == "/api/focus":
                    node = (parse_qs(u.query).get("node") or [""])[0]
                    tree = build_focus(load(), node)
                    if tree is None:
                        self._json({"error": f"节点不存在: {node}"}, 404)
                    else:
                        self._json(tree)
                elif u.path == "/api/drilldown":
                    # 公式钻取卡片: 公式头+结果+输入插槽, 只渲染一层, 端上逐节点拉取
                    node = (parse_qs(u.query).get("node") or [""])[0]
                    card = build_drilldown(load(), node)
                    if card is None:
                        self._json({"error": f"节点不存在: {node}"}, 404)
                    else:
                        self._json(card)
                else:
                    self._send(404, "not found", "text/plain")
            except Exception as e:  # 把异常回给前端而不是崩服务
                self._json({"error": str(e)}, 500)

    return Handler


def serve(sources_dir, operators_dir, host, port, samples, seed):
    handler = _make_handler(sources_dir, operators_dir, samples, seed)
    try:
        httpd = ThreadingHTTPServer((host, port), handler)
    except OSError as e:
        # 端口被占用最常见：多半已有一个 serve 在跑。改数据不用重启，直接刷新浏览器即可。
        print(f"端口 {host}:{port} 起不来（{e}）。")
        print("多半已有一个 serve 在跑——改完数据不用重启，回浏览器按 F5 刷新即可（每次请求都重读磁盘）。")
        print(f"若确实要另起一个，换端口：python -m cgraph.cli serve --port {port + 1}")
        return
    print(f"CausalGraph 网页已启动: http://{host}:{port}/  (Ctrl+C 停止)")
    print("提示：改完 data/ 下的节点/算子不用重启，回浏览器 F5 刷新即可（每次请求都重新从磁盘读图）。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        httpd.server_close()
