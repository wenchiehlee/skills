#!/bin/bash
# ⚠️ 已停用：gemini-cli 的消費者 OAuth 登入已於 2026-06-18 被 Google 終止
# （`gemini auth login` 會回傳 invalid_grant / exitCode 41）。
# `/gemini/exec` 現已改走 GEMINI_API_KEY 直連 Gemini API，不再需要這支腳本。
# 保留於此僅供歷史參考；請改到 GitHub repo Secrets 設定 GEMINI_API_KEY。
set -e

NAS_HOST="newton.tail28f10.ts.net"
NAS_USER="wjlee"                                          # 修改為你的 NAS 使用者名稱
NAS_SSH_PORT="22"                                         # NAS 本身的 SSH port（非容器的 2222）
NAS_GEMINI_PATH="/volume1/docker/Llm-Cli-APIServer/gemini-auth/"
CONTAINER_NAME="llm-cli-api-server"

echo "=== Step 1: Gemini CLI 重新登入 ==="
gemini auth login

echo ""
echo "=== Step 2: 複製 token 到 NAS ==="
scp -P "$NAS_SSH_PORT" -r ~/.gemini/. "$NAS_USER@$NAS_HOST:$NAS_GEMINI_PATH"

echo ""
echo "=== Step 3: 重啟 container ==="
ssh -p "$NAS_SSH_PORT" "$NAS_USER@$NAS_HOST" "docker restart $CONTAINER_NAME"

echo ""
echo "=== 完成！驗證 Gemini CLI 狀態 ==="
curl -s "https://api.wenchiehlee.synology.me:8443/gemini/status" | python3 -m json.tool
