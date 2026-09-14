#!/usr/bin/env bash
# 登录窗口 + 自动接刷课 + 刷满后自动拉证书（三段链式）
# 用法: bash jxjy_chain_login_study_cert.sh [窗口等待分钟=90] [刷课时长分钟=240] [证书等待分钟=180]
# 作用:
#   1) 弹出 Chrome 登录窗口长时间等待；检测到登录成功(jxjy_login_success.flag)即刷新 jxjy_state.json
#   2) 自动启动刷课会话，把剩余课程播完（"整门课看完才入账"，跨过 90 即停）
#   3) 刷课结束后若登录态仍有效，自动启动证书拉取（轮询平台直到出现证明按钮并下载 PDF）
# 用户只需在弹窗里扫码/短信登录一次，后续全自动，无需 agent 值守。
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
PY="C:/Users/admin/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
WAIT_MIN="${1:-90}"
STUDY_MIN="${2:-240}"
CERT_MIN="${3:-180}"
LOG="$DIR/jxjy_chain.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

log "=== 三段链式启动：登录窗口${WAIT_MIN}分 → 刷课${STUDY_MIN}分 → 证书轮询${CERT_MIN}分 ==="
rm -f jxjy_login_success.flag
"$PY" jxjy_login_window.py --wait "$WAIT_MIN" >> jxjy_login_window_chain.log 2>&1

if [ ! -f jxjy_login_success.flag ]; then
  log "=== LOGIN_TIMEOUT 未检测到登录，整条链路未启动 ==="
  exit 0
fi

log "登录成功（已刷新 jxjy_state.json），启动刷课 ${STUDY_MIN} 分钟"
"$PY" jxjy_daily_study.py "$STUDY_MIN" >> jxjy_study.log 2>&1
log "刷课会话结束，详见 jxjy_study_report.json"

# 第三段：刷课后拉证书（登录态应仍新鲜，<9h）
log "启动证书自动拉取（轮询平台至达标并下载 PDF，最多 ${CERT_MIN} 分钟）"
"$PY" jxjy_download_cert.py "$CERT_MIN" >> jxjy_download_cert_chain.log 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  log "证书已成功拉取并保存到 继续教育证明/ 与项目根"
else
  log "证书拉取退出码=$rc（0=成功 2=登录失效 3=超时 4=找不到按钮），详见 jxjy_download_cert_chain.log"
fi
log "=== 三段链式全部结束 ==="
