# 터미널 창을 띄우지 않고 로컬 API와 웹 UI를 시작합니다.
# 이미 포트를 사용 중인 서비스는 건너뛰므로 반복 실행해도 안전합니다.

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Join-Path $projectRoot ".venv\Scripts\python.exe"

function Test-ListeningPort {
    param([int]$Port)

    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-ListeningPort -Port 8000)) {
    if (-not (Test-Path -LiteralPath $pythonExecutable)) {
        throw "Prepare the project .venv first; see README.md."
    }
    Start-Process -FilePath $pythonExecutable `
        -ArgumentList "-m uvicorn app.api.main:app --reload" `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $projectRoot "api-local.stdout.log") `
        -RedirectStandardError (Join-Path $projectRoot "api-local.stderr.log")
}

if (-not (Test-ListeningPort -Port 5174)) {
    Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run dev" `
        -WorkingDirectory (Join-Path $projectRoot "web") `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $projectRoot "web-local.stdout.log") `
        -RedirectStandardError (Join-Path $projectRoot "web-local.stderr.log")
}
