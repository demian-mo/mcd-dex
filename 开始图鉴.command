#!/bin/bash
# 麦麦图鉴 · 双击即玩
# 自动挑选可用的 Python 3（系统自带即可，零依赖）
cd "$(dirname "$0")"

PY=""
for c in python3 /usr/bin/python3 /Users/yd/.workbuddy/binaries/python/versions/3.13.12/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
    PY="$c"; break
  fi
done

if [ -z "$PY" ]; then
  echo "⚠️ 没找到 Python 3.9+，请先安装 Python（python.org 下载即可）"
  read -r -p "按回车关闭..." _
  exit 1
fi

exec "$PY" play.py
