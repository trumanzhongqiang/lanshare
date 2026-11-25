# -*- coding: utf-8 -*-
# LanShare 卸载脚本：移除右键菜单、开机自启、停止服务；
# 加 -RemoveFiles 同时删除程序与分享记录（shares.json）。
param([switch]$RemoveFiles)

$ErrorActionPreference = 'Continue'
$Install = Join-Path $env:LOCALAPPDATA 'LanShare'

# 1. 右键菜单
foreach ($k in 'Software\Classes\*\shell\LanShare',
               'Software\Classes\Directory\shell\LanShare',
               'Software\Classes\Directory\Background\shell\LanShare') {
    try {
        [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($k)
        Write-Host "已移除 $k"
    } catch { Write-Host "跳过 $k（不存在）" }
}

# 2. 开机自启
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'LanShare Server.lnk'
if (Test-Path $lnk) { Remove-Item $lnk; Write-Host '已移除开机自启' }

# 3. 停止服务（按端口找 PID，不误伤其他 Python）
$lines = netstat -ano | Select-String ':8000\s.*LISTENING'
foreach ($l in $lines) {
    $pid_ = ($l.ToString().Trim() -split '\s+')[-1]
    if ($pid_ -match '^\d+$' -and $pid_ -ne '0') {
        taskkill /PID $pid_ /F 2>$null
        Write-Host "已停止服务进程 PID $pid_"
    }
}

# 4. 可选：删除程序文件与分享记录
if ($RemoveFiles) {
    if (Test-Path $Install) { Remove-Item $Install -Recurse -Force; Write-Host "已删除 $Install" }
} else {
    Write-Host "保留了 $Install（含分享记录）。加 -RemoveFiles 可一并删除。"
}
Write-Host '卸载完成。' -ForegroundColor Green
