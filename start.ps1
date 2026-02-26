param(
    [switch]$SkipInstall,
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[AlphaSeeker] 未检测到虚拟环境，正在创建 .venv ..." -ForegroundColor Yellow
    py -3 -m venv .venv
}

if (-not (Test-Path $VenvPython)) {
    throw "未找到虚拟环境 Python：$VenvPython"
}

if (-not $SkipInstall) {
    Write-Host "[AlphaSeeker] 安装/更新依赖 ..." -ForegroundColor Cyan
    & $VenvPython -m pip install -r requirements.txt
}

Write-Host "[AlphaSeeker] 启动预览页面：http://localhost:$Port" -ForegroundColor Green
& $VenvPython -m streamlit run src/alphaseeker/preview_app.py --server.port $Port
