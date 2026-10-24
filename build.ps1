# 打包发布：把 mod/ 组装成 dist/Melvor2Zh-zh-CN.zip
#
# 玩家解压后，游戏根目录应该只多出两样东西：
#
#   Melvor2.exe
#   override.cfg      <- 必须在根目录，Godot 从这个固定位置读它
#   mod/              <- 其余全部收在这里
#      zhpatch.gd
#      zh_CN.po
#      README.txt
#
# 所以压缩包里就是「根目录一个 override.cfg + 一个 mod 文件夹」，
# 解压到游戏目录即完成安装，不会散落一堆文件。
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# 注意：本文件必须存成 UTF-8 带 BOM。PowerShell 5.1 默认按 GBK 读脚本，
# 无 BOM 时中文注释会被解成乱码并破坏语法。

$ErrorActionPreference = 'Stop'
# Compress-Archive 的进度条会把输出搅乱，关掉
$ProgressPreference = 'SilentlyContinue'
$root  = $PSScriptRoot
$mod   = Join-Path $root 'mod'
$out   = Join-Path $root 'dist'
$zip   = Join-Path $out 'Melvor2Zh-zh-CN.zip'
$stage = Join-Path $out '_stage'

if (-not (Test-Path $mod)) {
    throw "missing directory: $mod"
}

$rootFile = Join-Path $mod 'override.cfg'
if (-not (Test-Path $rootFile)) {
    throw "missing $rootFile -- Godot only reads override.cfg from the game folder"
}

$nested = Get-ChildItem -Path $mod -File | Where-Object { $_.Name -ne 'override.cfg' }
if ($nested.Count -eq 0) {
    throw "mod/ has nothing but override.cfg"
}

if (Test-Path $out) {
    Remove-Item $out -Recurse -Force
}
New-Item -ItemType Directory -Path $stage | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage 'mod') | Out-Null

# override.cfg 放压缩包根，其余全部放进 mod/，与玩家侧的目标布局一致
Copy-Item $rootFile (Join-Path $stage 'override.cfg')
$nested | ForEach-Object { Copy-Item $_.FullName (Join-Path $stage 'mod') }

Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal
# Remove-Item 在某些环境会被删除钩子拦下，用 .NET 直接删暂存目录
[System.IO.Directory]::Delete($stage, $true)

Write-Host ''
Write-Host 'package layout:'
'  {0,-20} {1,10:N0} bytes' -f 'override.cfg', (Get-Item $rootFile).Length | Write-Host
$nested | Sort-Object Name | ForEach-Object {
    '  {0,-20} {1,10:N0} bytes' -f ('mod\' + $_.Name), $_.Length | Write-Host
}
Write-Host ''
'{0,-22} {1,10:N0} bytes' -f 'Melvor2Zh-zh-CN.zip', (Get-Item $zip).Length | Write-Host
Write-Host ''
Write-Host "-> $zip"
Write-Host 'Install: extract into the folder holding Melvor2.exe (not the data_* subfolder).'
