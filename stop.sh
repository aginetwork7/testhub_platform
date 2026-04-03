#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DC=(docker compose --env-file .env)
if ! docker info >/dev/null 2>&1; then
	if sudo -n docker info >/dev/null 2>&1; then
		DC=(sudo docker compose --env-file .env)
	else
		echo "[testhub] 无法访问 Docker daemon。"
		echo "[testhub] 请执行：sudo usermod -aG docker $USER && newgrp docker"
		echo "[testhub] 或者使用 sudo 运行本脚本。"
		exit 1
	fi
fi

echo "[testhub] 停止并移除 MySQL 和 Redis 容器..."
"${DC[@]}" stop mysql redis || true
"${DC[@]}" rm -f mysql redis || true

echo "[testhub] 停止完成。"
