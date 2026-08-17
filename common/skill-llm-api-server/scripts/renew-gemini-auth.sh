#!/bin/bash
# 在筆電上執行此腳本以更新 Gemini CLI OAuth token 並同步到 NAS
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
