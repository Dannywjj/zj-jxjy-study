#!/usr/bin/env python3
"""
继续教育刷课自动关机看门狗

判定逻辑（任一满足即触发）：
  ① 刷课任务自然结束 → status ∈ {completed, all_courses_done}
  ② 当前时间 ≥ 次日 03:00（本任务启动后 7 小时内强制兜底）

执行动作：shutdown /s /t 60 （60 秒缓冲，用户可手动 shutdown /a 取消）

启动方式（前台）：
  python jxjy_auto_shutdown.py

退出码：
  0 = 已发出关机指令（正常）
  1 = 异常退出
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

BASE = r"C:\Users\admin\WorkBuddy\2026-09-02-15-25-42\.workbuddy"
REPORT = os.path.join(BASE, "jxjy_study_report.json")
LOG = os.path.join(BASE, "jxjy_shutdown.log")
CHECK_INTERVAL = 30  # 秒

# 兜底时间：次日 3 点（绝对时间）
# 在脚本启动时算一次，跨过午夜后仍按"启动次日 03:00"算
START_TIME = datetime.now()
FORCE_OFF_TIME = (START_TIME + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)

DONE_STATUSES = {"completed", "all_courses_done"}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check_study_done():
    """刷课任务是否自然完成"""
    if not os.path.exists(REPORT):
        return False, "report_missing"
    try:
        # mtime 在 1 小时内才算"最近完成的报告"
        mtime = datetime.fromtimestamp(os.path.getmtime(REPORT))
        if (datetime.now() - mtime).total_seconds() > 3600:
            return False, "report_too_old"
        with open(REPORT, encoding="utf-8") as f:
            data = json.load(f)
        status = data.get("status")
        if status in DONE_STATUSES:
            return True, f"status={status}"
        return False, f"status={status}"
    except (json.JSONDecodeError, OSError) as e:
        return False, f"err={e}"


def is_force_time():
    """是否到达次日 3 点强制关机时间"""
    return datetime.now() >= FORCE_OFF_TIME


def trigger_shutdown(reason):
    log(f"触发关机：{reason}")
    log(f"执行命令: shutdown /s /t 60 /c \"继续教育学习完毕，自动关机（{reason}）。如需取消请在 60 秒内执行 shutdown /a\"")
    try:
        subprocess.run(
            ["shutdown", "/s", "/t", "60",
             "/c", f"继续教育学习完毕，自动关机（{reason}）。如需取消请在 60 秒内执行 shutdown /a"],
            check=False
        )
    except Exception as e:
        log(f"shutdown 调用失败: {e}")
        return False
    return True


def main():
    log("=== 自动关机看门狗启动 ===")
    log(f"兜底时间（次日 03:00）：{FORCE_OFF_TIME.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"判定规则：")
    log(f"  ① 刷课任务 status ∈ {DONE_STATUSES} → 立即关机")
    log(f"  ② 当前时间 ≥ {FORCE_OFF_TIME.strftime('%H:%M')} → 强制关机（兜底）")
    log(f"  缓冲：60 秒（用户可执行 shutdown /a 取消）")
    log(f"")

    iteration = 0
    while True:
        iteration += 1
        # 条件 1：刷课任务自然结束
        done, reason = check_study_done()
        if done:
            log(f"第 {iteration} 次检查：刷课已完成（{reason}）")
            if trigger_shutdown(f"刷课已完成 ({reason})"):
                return 0
        # 条件 2：到达兜底时间
        if is_force_time():
            log(f"第 {iteration} 次检查：到达兜底时间（次日 03:00）")
            if trigger_shutdown("到达兜底时间次日 03:00"):
                return 0

        if iteration % 10 == 1:
            remain = FORCE_OFF_TIME - datetime.now()
            hrs = int(remain.total_seconds() // 3600)
            mins = int((remain.total_seconds() % 3600) // 60)
            log(f"第 {iteration} 次检查：刷课未完成，距兜底 {hrs}h{mins}min")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("用户中断（Ctrl+C），退出看门狗")
        sys.exit(0)