#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  I-Ching — 一键安装 & 启动脚本
# ============================================================

PORT="${PORT:-8000}"
VENV_DIR=".venv"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$PROJECT_DIR"

# ---------- 颜色输出 ----------
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*"; }

# ---------- 检查 Python ----------
if ! command -v python3 &>/dev/null; then
    red "未找到 python3，请先安装 Python 3.10+"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
yellow "Python 版本: $PY_VERSION"

# ---------- 创建虚拟环境 ----------
if [[ ! -d "$VENV_DIR" ]]; then
    yellow "创建虚拟环境..."
    if command -v uv &>/dev/null; then
        uv venv "$VENV_DIR"
    else
        python3 -m venv "$VENV_DIR"
    fi
    green "虚拟环境已创建"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# ---------- 安装依赖 ----------
yellow "安装依赖..."
if command -v uv &>/dev/null; then
    uv pip install -r backend/requirements.txt -q
else
    pip install -r backend/requirements.txt -q
fi
green "依赖安装完成"

# ---------- LLM 配置 ----------
ENV_FILE="$PROJECT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    yellow "加载已有配置 (.env)..."
    set -a
    source "$ENV_FILE"
    set +a
    green "LLM: $LLM_BASE_URL | 模型: $LLM_MODEL"
else
    yellow "首���运行，请配置 LLM 连接信息："
    yellow "(支持任何 OpenAI 兼容 API：LM Studio / Ollama / OpenAI / DeepSeek 等)"
    yellow "(直接回车使用默认值)"
    echo ""

    read -rp "LLM API Base URL [http://localhost:1234/v1]: " input_url
    LLM_BASE_URL="${input_url:-http://localhost:1234/v1}"

    read -rp "LLM API Key [lm-studio]: " input_key
    LLM_API_KEY="${input_key:-lm-studio}"

    read -rp "模型名称 [google/gemma-4-26b-a4b]: " input_model
    LLM_MODEL="${input_model:-google/gemma-4-26b-a4b}"

    cat > "$ENV_FILE" <<ENVEOF
LLM_BASE_URL=$LLM_BASE_URL
LLM_API_KEY=$LLM_API_KEY
LLM_MODEL=$LLM_MODEL
ENVEOF

    green "配置已保存到 .env（修改配置请编辑此文件或删除后重新运行）"
    export LLM_BASE_URL LLM_API_KEY LLM_MODEL
fi

# ---------- 检查 LLM 服务 ----------
if curl -s --connect-timeout 2 "${LLM_BASE_URL}/models" &>/dev/null; then
    green "LLM 服务已连接 ($LLM_BASE_URL)"
else
    yellow "提示: LLM 服务未检��到 ($LLM_BASE_URL)"
    yellow "AI 卦辞解读功能��要 LLM 服��运行，其他功��不受影响"
fi

# ---------- 启动服务 ----------
green "=========================================="
green "  I-Ching启动中..."
green "  访问地址: http://localhost:${PORT}"
green "  按 Ctrl+C 停止"
green "=========================================="

exec uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" --reload
