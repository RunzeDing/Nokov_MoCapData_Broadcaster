# Build NokovBroadcaster.exe (single file, no Python installation required).
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Console   # chatty build
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Clean     # wipe build/ dist/
#
# Output: dist\NokovBroadcaster.exe

[CmdletBinding()]
param(
    [switch]$Console,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== NokovBroadcaster 打包 ==" -ForegroundColor Cyan
Write-Host "项目目录: $root"

# --- pick a Python interpreter --------------------------------------------- #
$python = $null
foreach ($candidate in @("py -3.8", "py -3", "python")) {
    $parts = $candidate.Split(" ")
    $exe = Get-Command $parts[0] -ErrorAction SilentlyContinue
    if (-not $exe) { continue }
    $args = @()
    if ($parts.Length -gt 1) { $args += $parts[1..($parts.Length - 1)] }
    try {
        $version = & $parts[0] @args -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($version) {
            $python = $candidate
            Write-Host "使用 Python: $candidate ($version)"
            break
        }
    } catch { }
}
if (-not $python) { throw "找不到可用的 Python 解释器。" }

function Invoke-Py {
    param([string[]]$Arguments)
    $parts = $python.Split(" ")
    & $parts[0] @($parts[1..($parts.Length - 1)]) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "命令失败 ($LASTEXITCODE): $($Arguments -join ' ')" }
}

# --- prerequisites --------------------------------------------------------- #
Invoke-Py @("-c", "import PyInstaller, PySide2; print('PyInstaller', PyInstaller.__version__, '/ PySide2', PySide2.__version__)")

# --- icon ------------------------------------------------------------------ #
Invoke-Py @("tools\make_icon.py")

# --- clean ----------------------------------------------------------------- #
if ($Clean) {
    foreach ($path in @("build", "dist")) {
        if (Test-Path $path) { Remove-Item $path -Recurse -Force }
    }
    Write-Host "已清理 build/ 与 dist/"
}

# --- build ----------------------------------------------------------------- #
if ($Console) { $env:NB_CONSOLE = "1" } else { Remove-Item Env:\NB_CONSOLE -ErrorAction SilentlyContinue }

Invoke-Py @("-m", "PyInstaller", "--noconfirm", "--clean", "NokovBroadcaster.spec")

$exe = Join-Path $root "dist\NokovBroadcaster.exe"
if (-not (Test-Path $exe)) { throw "打包失败：未生成 $exe" }

# 在项目目录和上层目录各放一份，方便直接找到（每次打包都会刷新，不会过期）
$copies = @((Join-Path $root "NokovBroadcaster.exe"))
$parent = Split-Path -Parent $root
if ($parent) { $copies += (Join-Path $parent "NokovBroadcaster.exe") }
foreach ($copy in $copies) {
    try {
        Copy-Item $exe $copy -Force
    } catch {
        Write-Host "提示: 无法写入 $copy（可能正在运行），跳过" -ForegroundColor Yellow
    }
}

$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "打包完成: $exe ($size MB)" -ForegroundColor Green
Write-Host "可直接双击运行的文件：" -ForegroundColor Green
foreach ($copy in $copies) {
    if (Test-Path $copy) { Write-Host "   $copy" }
}
Write-Host "该 exe 可在未安装 Python 的 Windows 电脑上直接运行。"
Write-Host "设置文件位置: %APPDATA%\NokovBroadcaster\config.json"
Write-Host "如需绿色便携模式，在 exe 同目录放置一个空的 portable.flag 文件即可。"
