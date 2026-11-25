# LanShare

**Right-click any file or folder in Windows Explorer → get a LAN link, already in your clipboard.**

Open the link on any device on the same Wi-Fi — phone, tablet, another PC — no app to install on the receiving side, just a browser. Videos stream with full seek support.

```
select file(s) → right-click → "LanShare / 局域网分享"
→ http://192.168.x.x:8000/s/a3f9c2e1/video.mp4   (copied to clipboard)
→ open it on your phone
```

## Why

The existing tools each miss a piece of this workflow:

- **LocalSend / LANDrop** — great for device-to-device pushes, but *both sides need the app*, and there is no link you can paste into a chat.
- **dufs / miniserve / HFS** — solid HTTP file servers, but they serve a whole directory you pick on a CLI, and *nothing integrates into the Explorer context menu*.

LanShare combines the two: Explorer-first UX, per-file random-token links, zero setup on the receiver.

## Features

- 🖱️ **Explorer context menu** for files, folders, folder background, and multi-select (all links copied at once)
- 🔗 **Token-per-share URLs** — only what you explicitly shared is ever reachable; nobody can browse the rest of your disk
- 📋 Link lands in your **clipboard** + a confirmation popup with the URL
- ▶️ **Video streaming with Range support** — drag the progress bar on a 4 GB mp4 over Wi-Fi, it just works
- 📱 Mobile-friendly index page listing every current share
- 🚀 Background service auto-starts on boot; the right-click action revives it if it isn't running
- 🪟 No admin rights needed to install (only a one-time UAC prompt for the firewall rule)

## Install

Requirements: Windows 10/11, [Python 3.8+](https://www.python.org/downloads/) in `PATH` (the installer uses `pythonw.exe`).

```powershell
git clone https://github.com/trumanzhongqiang/lanshare.git
cd lanshare
powershell -ExecutionPolicy Bypass -File install.ps1
```

The installer:

1. copies `server.pyw` / `share.pyw` to `%LOCALAPPDATA%\LanShare`
2. registers the context-menu verb for files, directories and directory background
3. adds a Startup shortcut for the server
4. adds a firewall rule for TCP 8000 (one UAC prompt)
5. starts the server

Windows 11 shows the entry under "Show more options" (or Shift+right-click); Windows 10 shows it in the top-level menu.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File uninstall.ps1               # keep program files
powershell -ExecutionPolicy Bypass -File uninstall.ps1 -RemoveFiles   # remove everything
```

## How it works

| File | Role |
|---|---|
| `server.pyw` | Resident HTTP server (port 8000). Reads `shares.json` on every request — revoke a share by deleting its entry, no restart needed. Serves files with `Accept-Ranges`/206 for seeking. |
| `share.pyw` | Context-menu action. Registers the path with a fresh 8-hex token, builds the URL, copies it, shows a popup. Multi-select instances converge via a pending-file handshake so you get one clipboard payload. |
| `install.ps1` / `uninstall.ps1` | Registry verbs (HKCU), Startup shortcut, firewall rule, service lifecycle. |

Revoke everything: empty the `shares` array in `%LOCALAPPDATA%\LanShare\shares.json`.

## Notes & troubleshooting

- **LAN only, by design.** Links contain a private IP and never leave your home network.
- **IP changed by the router?** Old links break — right-click the file again. (Fix it permanently with a DHCP reservation for your PC.)
- **Phone can't connect?** Almost always the firewall profile: the installer opens TCP 8000 for the *private* profile. If your Wi-Fi is categorized as *public*, re-run `install.ps1`, or change the network category.
- **Formats** — mp4/webm/m4v play natively in browsers; for mkv/avi open the link in [VLC](https://www.videolan.org/) (Network Stream) on the receiving device.

## Security model

- Each share gets a random 32-bit token; unknown tokens get a 404 and reveal nothing.
- Directory traversal outside the shared root is blocked.
- The server binds LAN interfaces only in practice (it never does port mapping / UPnP).
- Anyone on the LAN *with the link* can download — treat the link like a physical copy of the file. Revoke by editing `shares.json`.

## License

[MIT](LICENSE) · Built because nothing on GitHub quite did this. PRs welcome — QR-code popup and a receive/upload mode are the obvious next features.

---

# 中文说明

**在资源管理器里右键任意文件/文件夹 → 链接已复制到剪贴板。** 同一 Wi-Fi 下的手机、平板、电脑浏览器直接打开，接收方无需安装任何东西，视频在线播、可随意拖进度条。

- 每次分享生成随机令牌链接，未分享的内容一律 404，不暴露磁盘其他内容
- 支持多选（一次复制全部链接）、文件夹（列表页）、手机索引页 `http://<电脑IP>:8000/`
- 取消分享：编辑 `%LOCALAPPDATA%\LanShare\shares.json` 删除对应条目，即时生效
- 安装/卸载见上方英文段落，要求 Windows 10/11 + Python 3.8+

对比：LocalSend 要双方装 App、给不了链接；dufs/miniserve 要手动起服务、共享整个目录、没有右键集成。LanShare 把这条链路补全了。
