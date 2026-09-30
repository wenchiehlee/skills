#!/bin/bash
# 在 NAS container 內重新登入 agy（Antigravity CLI）的 OAuth。
#
# 跟舊版 renew-gemini-auth.sh 不同：agy 的登入是直接在 container 裡跑（container
# 印出授權網址，在自己的瀏覽器打開完成登入），不是在筆電登入後再 scp token 過去。
# 只要 docker-compose.yml 裡的 ./gemini-auth:/root/.gemini 掛載點涵蓋 agy 的 token
# 路徑，登入完成後 token 就已經在 NAS host 上持久化，不需要額外複製。
set -e

NAS_HOST="newton.tail28f10.ts.net"
NAS_USER="wjlee"                                          # 修改為你的 NAS 使用者名稱
NAS_SSH_PORT="22"                                         # NAS 本身的 SSH port（非容器的 2222）
CONTAINER_NAME="llm-cli-api-server"

echo "=== Step 1: 進入 NAS container 執行 agy 登入 ==="
echo "接下來會進入互動式 SSH + docker exec，請依畫面指示打開瀏覽器完成 Google 帳號登入。"
ssh -t -p "$NAS_SSH_PORT" "$NAS_USER@$NAS_HOST" \
    "docker exec -it $CONTAINER_NAME agy"

echo ""
echo "=== Step 2: 驗證 agy 狀態 ==="
curl -s "https://api.wenchiehlee.synology.me:8443/gemini/status" | python3 -m json.tool

echo ""
echo "若 primary.installed 為 true，代表 agy 已可用；建議額外測試一次非互動模式："
echo "  ssh -p $NAS_SSH_PORT $NAS_USER@$NAS_HOST \"docker exec $CONTAINER_NAME agy -p 'say hello'\""
