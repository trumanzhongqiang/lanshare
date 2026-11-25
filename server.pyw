# -*- coding: utf-8 -*-
# LanShare server — 令牌制局域网文件分享服务器
# 只有显式分享过的文件/文件夹（记录在 shares.json，带随机令牌）才能被访问，
# 局域网内其他人无法浏览未分享的内容。完整支持 HTTP Range 断点续传。
import json
import os
import re
import html
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, quote

BASE = os.path.dirname(os.path.abspath(__file__))
SHARES_FILE = os.path.join(BASE, 'shares.json')
PORT = 8000
TOKEN_RE = re.compile(r'^/s/([0-9a-f]+)(/.*)?$')

MIME = {
    '.mp4': 'video/mp4', '.m4v': 'video/x-m4v', '.mkv': 'video/x-matroska',
    '.avi': 'video/x-msvideo', '.mov': 'video/quicktime', '.ts': 'video/mp2t',
    '.webm': 'video/webm', '.flv': 'video/x-flv', '.wmv': 'video/x-ms-wmv',
    '.mp3': 'audio/mpeg', '.flac': 'audio/flac', '.m4a': 'audio/mp4',
    '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.wma': 'audio/x-ms-wma',
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
    '.txt': 'text/plain; charset=utf-8', '.srt': 'text/plain; charset=utf-8',
    '.ass': 'text/plain; charset=utf-8', '.vtt': 'text/vtt; charset=utf-8',
    '.pdf': 'application/pdf', '.zip': 'application/zip',
    '.7z': 'application/x-7z-compressed', '.rar': 'application/vnd.rar',
    '.iso': 'application/x-iso9660-image',
}

CHUNK = 512 * 1024  # 512KB 分块发送


def load_shares():
    try:
        with open(SHARES_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return [s for s in data.get('shares', []) if isinstance(s, dict)]
    except Exception:
        return []


def find_share(token):
    for s in load_shares():
        if s.get('token') == token:
            return s
    return None


def h(size):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024:
            return f'{size:.0f}{unit}' if unit == 'B' else f'{size:.1f}{unit}'
        size /= 1024
    return f'{size:.1f}PB'


PAGE_HEAD = ('<!doctype html><meta charset="utf-8"><meta name="viewport" '
             'content="width=device-width,initial-scale=1"><title>局域网分享</title>'
             '<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:24px auto;'
             'padding:0 16px}li{margin:8px 0;line-height:1.5}small{color:#888}'
             'a{color:#0a6cd6;text-decoration:none}a:active{color:#e65100}</style>')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'LanShare/1.0'
    disable_nagle_algorithm = True

    # ---------- 路由 ----------
    def do_GET(self):
        self.route(True)

    def do_HEAD(self):
        self.route(False)

    def route(self, send_body):
        path = unquote(self.path.split('?', 1)[0].split('#', 1)[0])
        if path == '/__ping':
            return self._text(200, 'lan-share-server', send_body)
        m = TOKEN_RE.match(path)
        if m:
            return self.serve_share(m.group(1), (m.group(2) or '/').strip('/'), send_body)
        if path in ('', '/', '/index.html'):
            return self.index_page(send_body)
        return self._text(404, 'Not Found', send_body)

    # ---------- 分享内容 ----------
    def serve_share(self, token, rel, send_body):
        share = find_share(token)
        if not share:
            return self._text(404, '链接无效或已取消分享', send_body)
        root = share.get('path', '')
        if not os.path.exists(root):
            return self._text(404, '分享的文件已被移动或删除', send_body)
        if os.path.isfile(root):
            return self.send_file(root, send_body)
        # 文件夹分享：允许访问其下的子路径
        full = os.path.abspath(os.path.join(root, os.path.normpath(rel))) if rel else os.path.abspath(root)
        rl = root.lower().rstrip('\\') + '\\'
        if not (full.lower() == root.lower() or full.lower().startswith(rl)):
            return self._text(403, '禁止访问分享范围之外的路径', send_body)
        if os.path.isdir(full):
            return self.dir_listing(full, token, rel, send_body)
        if os.path.isfile(full):
            return self.send_file(full, send_body)
        return self._text(404, '未找到: ' + rel, send_body)

    # ---------- 文件发送（含 Range） ----------
    def send_file(self, full, send_body):
        size = os.path.getsize(full)
        ctype = MIME.get(os.path.splitext(full)[1].lower(), 'application/octet-stream')

        start, end, partial = 0, size - 1, False
        rng = self.headers.get('Range')
        if rng:
            m = re.match(r'bytes=(\d*)-(\d*)', rng.strip())
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = int(m.group(2))
                elif m.group(2):  # bytes=-N 后缀形式
                    start = max(0, size - int(m.group(2)))
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                end = min(end, size - 1)
                partial = True

        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(length))
        if partial:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()

        if send_body and length > 0:
            with open(full, 'rb') as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        return  # 播放器中断/拖动进度属于正常情况
                    remaining -= len(chunk)

    # ---------- 页面 ----------
    def dir_listing(self, dir_path, token, rel, send_body):
        prefix = '/s/' + token + ('/' + quote(rel) if rel else '')
        rows = []
        if rel:
            parent = os.path.dirname(rel)
            target = '/s/' + token + ('/' + quote(parent) if parent else '')
            rows.append(f'<li><a href="{target}">[..] 上一级</a></li>')
        try:
            names = sorted(os.listdir(dir_path), key=str.lower)
        except OSError as e:
            return self._text(500, f'无法读取目录: {e}', send_body)
        for name in names:
            fp = os.path.join(dir_path, name)
            if os.path.isdir(fp):
                rows.append(f'<li>📁 <a href="{prefix}/{quote(name)}/">{html.escape(name)}/</a></li>')
            else:
                try:
                    sz = h(os.path.getsize(fp))
                except OSError:
                    sz = '?'
                rows.append(f'<li>📄 <a href="{prefix}/{quote(name)}">{html.escape(name)}</a> '
                            f'<small>{sz}</small></li>')
        body = (PAGE_HEAD + f'<h3>📁 {html.escape(os.path.basename(dir_path) or dir_path)}</h3><ul>'
                + ''.join(rows) + '</ul>').encode('utf-8')
        self._bytes(200, body, 'text/html; charset=utf-8', send_body)

    def index_page(self, send_body):
        shares = load_shares()
        rows = []
        for s in shares:
            p = s.get('path', '')
            name = os.path.basename(p.rstrip('\\')) or p
            created = s.get('created', '')
            if os.path.isdir(p):
                href = f'/s/{s["token"]}/'
            else:
                href = f'/s/{s["token"]}/{quote(name)}'
            rows.append(f'<li><a href="{href}">{html.escape(name)}</a><br>'
                        f'<small>{html.escape(p)} · {html.escape(created)}</small></li>')
        tip = ('<p><small>在电脑上右键文件 →「局域网分享」即可新增链接</small></p>'
               if shares else '<p><small>还没有分享任何内容。在电脑上右键文件 →「局域网分享」。</small></p>')
        body = (PAGE_HEAD + '<h3>🔗 局域网分享</h3>' + tip + '<ul>' + ''.join(rows) + '</ul>').encode('utf-8')
        self._bytes(200, body, 'text/html; charset=utf-8', send_body)

    # ---------- 小工具 ----------
    def _text(self, code, msg, send_body):
        self._bytes(code, (PAGE_HEAD + f'<p>{html.escape(msg)}</p>').encode('utf-8'),
                    'text/html; charset=utf-8', send_body)

    def _bytes(self, code, body, ctype, send_body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # 静默访问日志


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    Server(('0.0.0.0', PORT), Handler).serve_forever()


if __name__ == '__main__':
    try:
        main()
    except OSError:
        pass  # 端口被占用（多半是已在运行的实例），静默退出
    except Exception:
        try:
            with open(os.path.join(BASE, 'server_error.log'), 'a', encoding='utf-8') as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
