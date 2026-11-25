# -*- coding: utf-8 -*-
# LanShare 右键动作：把文件/文件夹登记为分享，生成链接并复制到剪贴板，弹窗提示。
# 多选时 Windows 会为每个文件启动一个本进程实例，通过 pending_urls.txt 汇总后一次性复制。
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import socket
import msvcrt

BASE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(BASE, 'server.pyw')
SHARES_FILE = os.path.join(BASE, 'shares.json')
PENDING = os.path.join(BASE, 'pending_urls.txt')
PORT = 8000
CREATE_NO_WINDOW = 0x08000000


def lan_ip():
    """探测本机局域网 IP（UDP connect 不会真正发包，离线也能拿到路由表结果）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'
    finally:
        s.close()


def server_alive():
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/__ping', timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_server():
    if server_alive():
        return True
    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    subprocess.Popen(
        [pythonw, SERVER],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | CREATE_NO_WINDOW, close_fds=True,
        cwd=BASE)
    for _ in range(20):  # 最多等 4 秒
        if server_alive():
            return True
        time.sleep(0.2)
    return False


def update_shares(entry):
    """带锁地追加一条分享记录；锁用独立的锁文件，写入用临时文件+原子替换"""
    lock_path = SHARES_FILE + '.lock'
    with open(lock_path, 'w') as lockf:
        msvcrt.locking(lockf.fileno(), msvcrt.LK_LOCK, 1)  # 多开进程互斥
        try:
            try:
                with open(SHARES_FILE, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
            data.setdefault('shares', []).append(entry)
            tmp = SHARES_FILE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, SHARES_FILE)
        finally:
            lockf.seek(0)
            msvcrt.locking(lockf.fileno(), msvcrt.LK_UNLCK, 1)


def copy_clipboard(text):
    # URL 是纯 ASCII（中文文件名已百分号编码），clip.exe 可安全接收
    subprocess.run(['clip'], input=text.encode('ascii', 'ignore'),
                   creationflags=CREATE_NO_WINDOW, check=False)


def ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def popup(msg, seconds=5):
    ps = ("$ws = New-Object -ComObject WScript.Shell; "
          f"$ws.Popup({ps_quote(msg)}, {seconds}, {ps_quote('局域网分享')}, 64) | Out-Null")
    subprocess.run(['powershell', '-NoProfile', '-WindowStyle', 'Hidden', '-Command', ps],
                   creationflags=CREATE_NO_WINDOW, check=False)


def main():
    paths = [p for p in sys.argv[1:] if p and os.path.exists(p)]
    if not paths:
        popup('没有找到可分享的文件（路径不存在）')
        return 1

    if not ensure_server():
        popup(f'分享服务启动失败。\n请手动运行：\n{SERVER}')
        return 1

    ip = lan_ip()
    urls = []
    for p in paths:
        token = secrets.token_hex(4)
        update_shares({'token': token,
                       'path': os.path.abspath(p),
                       'created': time.strftime('%Y-%m-%d %H:%M')})
        name = os.path.basename(p.rstrip('\\'))
        if os.path.isdir(p):
            # 文件夹：链接到根，token 后面跟名字会被当成子路径
            urls.append(f'http://{ip}:{PORT}/s/{token}/')
        else:
            urls.append(f'http://{ip}:{PORT}/s/{token}/{urllib.parse.quote(name)}')

    # —— 多选汇总：等 600ms 内没有新进程写入，视为稳定，一次性复制 ——
    with open(PENDING, 'a', encoding='utf-8') as f:
        f.write('\n'.join(urls) + '\n')
    last, stable_since, deadline = None, None, time.time() + 8
    while time.time() < deadline:
        time.sleep(0.25)
        try:
            with open(PENDING, encoding='utf-8') as f:
                cur = f.read()
        except FileNotFoundError:
            break  # 已被并行的实例处理完毕
        if cur == last:
            if stable_since and time.time() - stable_since > 0.6:
                break
        else:
            last, stable_since = cur, time.time()
    try:
        with open(PENDING, encoding='utf-8') as f:
            content = f.read()
        os.remove(PENDING)
    except FileNotFoundError:
        return 0  # 另一个实例已完成复制和提示
    all_urls = [l.strip() for l in content.splitlines() if l.strip()]
    if not all_urls:
        return 0

    copy_clipboard('\n'.join(all_urls))
    if len(all_urls) == 1:
        popup(f'已复制链接，去粘贴给别人吧：\n\n{all_urls[0]}')
    else:
        popup(f'已复制 {len(all_urls)} 个链接：\n\n' + '\n'.join(all_urls[:3])
              + ('\n…' if len(all_urls) > 3 else ''))
    if sys.stdout:  # pythonw 下无标准输出
        print('\n'.join(all_urls))  # 便于命令行调试
    return 0


if __name__ == '__main__':
    sys.exit(main())
