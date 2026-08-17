# 在筆電上執行此腳本以更新 Gemini CLI OAuth token 並同步到 NAS
# 執行方式：powershell -ExecutionPolicy Bypass -File Renew-GeminiAuth.ps1

$NAS_HOST      = "newton.tail28f10.ts.net"
$NAS_USER      = "wjlee"                          # 修改為你的 NAS 使用者名稱
$NAS_SSH_PORT  = "22"                             # NAS 本身的 SSH port
$NAS_GEMINI_PATH = "/volume1/docker/Llm-Cli-APIServer/gemini-auth/"
$CONTAINER_NAME  = "llm-cli-api-server"
$API_BASE        = "https://api.wenchiehlee.synology.me:8443"
$envLine = Get-Content "$PSScriptRoot\.env" -ErrorAction SilentlyContinue | Where-Object { $_ -match "^CODEX_API_KEY=" }
$API_KEY = if ($envLine) { ($envLine -split "=", 2)[1] } else { $env:CODEX_API_KEY }

# ── Step 1: 檢查 token 是否仍有效 ────────────────────────────────────────────
Write-Host "=== Step 1: 檢查 Gemini token 是否有效 ===" -ForegroundColor Cyan

$tokenValid = $false
try {
    $body = '{"prompt":"reply OK","json_mode":false}'
    $headers = @{ "X-API-Key" = $API_KEY; "Content-Type" = "application/json" }
    $resp = Invoke-WebRequest -Uri "$API_BASE/gemini/exec" `
                              -Method POST -Body $body -Headers $headers `
                              -TimeoutSec 30 -ErrorAction Stop
    $tokenValid = ($resp.StatusCode -eq 200)
} catch {
    $tokenValid = $false
}

if ($tokenValid) {
    Write-Host "Token 仍有效，無需更新。" -ForegroundColor Green
    exit 0
}

Write-Host "Token 失效或無法連線，開始更新流程..." -ForegroundColor Yellow

# ── Step 2: 重新登入 ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Step 2: Gemini CLI 重新登入（會開啟瀏覽器）===" -ForegroundColor Cyan
gemini auth login
if ($LASTEXITCODE -ne 0) {
    Write-Error "gemini auth login 失敗，中止。"
    exit 1
}

# ── Step 3: 複製 token 到 NAS ─────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Step 3: 複製 token 到 NAS ===" -ForegroundColor Cyan
$localGemini = "$env:USERPROFILE\.gemini\*"
scp -P $NAS_SSH_PORT -r $localGemini "${NAS_USER}@${NAS_HOST}:${NAS_GEMINI_PATH}"
if ($LASTEXITCODE -ne 0) {
    Write-Error "scp 失敗，請確認 NAS SSH 連線與路徑設定。"
    exit 1
}

# ── Step 4: 重啟 container ────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Step 4: 重啟 container ===" -ForegroundColor Cyan
ssh -p $NAS_SSH_PORT "${NAS_USER}@${NAS_HOST}" "docker restart $CONTAINER_NAME"
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker restart 失敗。"
    exit 1
}

# ── Step 5: 驗證 ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Step 5: 驗證 Gemini 狀態 ===" -ForegroundColor Cyan
Start-Sleep -Seconds 3
try {
    $check = Invoke-WebRequest -Uri "$API_BASE/gemini/status" -TimeoutSec 10 -ErrorAction Stop
    Write-Host ($check.Content | ConvertFrom-Json | ConvertTo-Json) -ForegroundColor Green
    Write-Host "完成！Gemini token 已成功更新。" -ForegroundColor Green
} catch {
    Write-Warning "驗證時無法連線（$_），請手動確認容器狀態。"
}
