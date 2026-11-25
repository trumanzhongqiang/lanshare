# -*- coding: utf-8 -*-
# LanShare 安装脚本：复制程序 → 注册右键菜单 → 开机自启 → 防火墙放行 → 启动服务
# 不需要管理员运行；唯独防火墙规则需要 UAC 提权一次（会自动弹出确认框）。
param([switch]$NoFirewall)

$ErrorActionPreference = 'Stop'
$Install = Join-Path $env:LOCALAPPDATA 'LanShare'
$RuleName = 'LanShare Server'

Write-Host "== LanShare 安装 ==" -ForegroundColor Cyan

# 1. 复制程序文件
New-Item -ItemType Directory -Path $Install -Force | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'server.pyw') $Install -Force
Copy-Item (Join-Path $PSScriptRoot 'share.pyw') $Install -Force
Write-Host "已复制程序到 $Install"

# 2. 定位 pythonw
$py = (Get-Command python -ErrorAction Stop).Source
$pyw = Join-Path (Split-Path $py) 'pythonw.exe'
if (-not (Test-Path $pyw)) { throw "找不到 pythonw.exe（应在 $(Split-Path $py)）" }
Write-Host "使用 $pyw"

# 3. 注册右键菜单（文件 / 文件夹 / 文件夹空白处），用 .NET API 避免路径通配问题
function Set-Verb([string]$subKey, [string]$argSpec) {
    $k = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($subKey)
    $k.SetValue('', '局域网分享')
    $k.SetValue('Icon', $pyw)
    $cmd = $k.CreateSubKey('command')
    $cmd.SetValue('', ('"{0}" "{1}" "{2}"' -f $pyw, (Join-Path $Install 'share.pyw'), $argSpec))
}
Set-Verb 'Software\Classes\*\shell\LanShare' '%1'
Set-Verb 'Software\Classes\Directory\shell\LanShare' '%1'
Set-Verb 'Software\Classes\Directory\Background\shell\LanShare' '%V'
Write-Host '已注册右键菜单：文件 / 文件夹 / 文件夹空白处 →「局域网分享」'

# 4. 开机自启（当前用户启动文件夹快捷方式，无需管理员）
$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup 'LanShare Server.lnk'
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = ('"{0}"' -f (Join-Path $Install 'server.pyw'))
$s.WorkingDirectory = $Install
$s.Description = 'LanShare 局域网文件分享服务'
$s.Save()
Write-Host "已添加开机自启：$lnk"

# 5. 防火墙放行 TCP 8000（专用网络），需要管理员；失败则请求 UAC
if (-not $NoFirewall) {
    $show = (netsh advfirewall firewall show rule name="$RuleName" 2>$null | Out-String)
    if ($show -notmatch '8000') {
        $args_ = @('advfirewall', 'firewall', 'add', 'rule', "name=$RuleName",
                   'dir=in', 'action=allow', 'protocol=TCP', 'localport=8000', 'profile=private')
        $null = netsh @args_ 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host '需要管理员权限添加防火墙规则，请在弹出的 UAC 窗口确认…' -ForegroundColor Yellow
            try {
                Start-Process netsh -Verb RunAs -ArgumentList $args_ -Wait
                Write-Host '防火墙规则已添加（TCP 8000 / 专用网络）'
            } catch {
                Write-Warning '防火墙规则未添加。首次运行服务时 Windows 会弹窗询问，选“允许”也可。'
            }
        } else {
            Write-Host '防火墙规则已添加（TCP 8000 / 专用网络）'
        }
    } else {
        Write-Host "防火墙规则已存在：$RuleName"
    }
}

# 6. 立即启动服务
$alive = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/__ping" -UseBasicParsing -TimeoutSec 1
    $alive = ($r.StatusCode -eq 200)
} catch {}
if (-not $alive) {
    Start-Process $pyw -ArgumentList ('"{0}"' -f (Join-Path $Install 'server.pyw')) -WorkingDirectory $Install
    foreach ($i in 1..15) {
        Start-Sleep -Milliseconds 400
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/__ping" -UseBasicParsing -TimeoutSec 1
            $alive = ($r.StatusCode -eq 200); if ($alive) { break }
        } catch {}
    }
}

if ($alive) {
    Write-Host ''
    Write-Host '✅ 安装完成，服务已在运行。' -ForegroundColor Green
    Write-Host '   用法：选中文件或文件夹 → 右键 →「显示更多选项」→「局域网分享」'
    Write-Host '   （Windows 10 直接在一级菜单；按住 Shift 右键也可直达）'
    Write-Host '   链接随即复制到剪贴板，手机在同一 Wi-Fi 下打开即可。'
} else {
    Write-Warning ("服务启动异常，请手动运行: $pyw `"$Install\server.pyw`"")
}
