#!/usr/bin/env python3
"""继续教育刷课 · 自动关机看门狗

用法一：指定关机时刻（推荐）
  python jxjy_auto_shutdown.py --at 09:00                      # 今天 09:00（已过则顺延明天）
  python jxjy_auto_shutdown.py --at 21:00 --date 2026-09-12    # 指定日期 2026-09-12 21:00
  python jxjy_auto_shutdown.py --at "2026-09-12 21:00"         # 等价写法
  python jxjy_auto_shutdown.py --after 300                     # 300 分钟后

  可叠加的"提前关机"条件（默认：指定了时刻就只按时间关机）：
    --on-all-done    仅当所有课程真正刷完时提前关机
                     （status ∈ completed / all_courses_done / done_no_more_courses，
                       或看板学分数据 15 分钟内刷新且总学分达标）
    --on-study-done  本次刷课会话结束（含 time_up 计时到点）时提前关机

用法二：无参数（旧行为）
  python jxjy_auto_shutdown.py
  → 刷课会话自然结束（completed / all_courses_done / time_up）
     或 到达"启动次日 03:00"兜底时间，任一满足即关机

执行动作：shutdown /s /t 60（60 秒缓冲，可 shutdown /a 取消）
退出码：0 = 已发出关机指令；1 = 异常退出
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(BASE, "jxjy_study_report.json")
DASH = os.path.join(BASE, "jxjy_dashboard_data.json")
LOG = os.path.join(BASE, "jxjy_shutdown.log")
CHECK_INTERVAL = 30  # 秒

# 所有课程真正刷完。
# 注意：done_no_more_courses = 学习中心已无可继续学习的课程，等价于"刷完了"。
# （刷课脚本在学分达标时会输出 all_courses_done；无课可刷时输出 done_no_more_courses。）
ALL_DONE_STATUSES = {"completed", "all_courses_done", "done_no_more_courses"}
# 本次刷课会话结束（含计时到点 time_up）
SESSION_END_STATUSES = ALL_DONE_STATUSES | {"time_up"}
# 学分达标视为完成的判据：看板数据 15 分钟内有更新 且 总学分 ≥ 目标
CREDIT_FRESH_MINUTES = 15


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def check_study_done(done_statuses):
    """刷课报告状态是否落入给定的"已完成"集合"""
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
        if status in done_statuses:
            return True, f"status={status}"
        return False, f"status={status}"
    except (json.JSONDecodeError, OSError) as e:
        return False, f"err={e}"


def check_credit_done():
    """学分是否已达标（总 ≥ 目标）且看板数据是新鲜的。

    作为 status 判定的补充：脚本若在"学分刚好达标"后因异常退出，
    status 可能停在 running/error，此时靠学分数据也能判定"刷完了"。
    要求 15 分钟内有更新，避免拿陈旧的看板数据误判而错误关机。
    """
    if not os.path.exists(DASH):
        return False, "dash_missing"
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(DASH))
        age_min = (datetime.now() - mtime).total_seconds() / 60
        if age_min > CREDIT_FRESH_MINUTES:
            return False, f"dash_stale({age_min:.0f}min)"
        with open(DASH, encoding="utf-8") as f:
            d = json.load(f)
        got = float(d.get("total", {}).get("got", 0))
        need = float(d.get("total", {}).get("need", 90))
        if need > 0 and got >= need - 0.01:
            return True, f"学分达标 {got}/{need}"
        return False, f"学分 {got}/{need}"
    except Exception as e:
        return False, f"err={e}"


def parse_target(args):
    """返回目标关机时间（datetime）。"""
    now = datetime.now()
    at = (args.at or "").strip().replace("T", " ")

    if at:
        # 写法 A：--at "YYYY-MM-DD HH:MM"
        if " " in at:
            date_part, time_part = at.split(" ", 1)
            hh, mm = (int(x) for x in time_part.split(":"))
            return datetime.strptime(date_part, "%Y-%m-%d").replace(
                hour=hh, minute=mm, second=0, microsecond=0)
        # 写法 B：--at HH:MM（+ 可选 --date）
        hh, mm = (int(x) for x in at.split(":"))
        if args.date:
            return datetime.strptime(args.date, "%Y-%m-%d").replace(
                hour=hh, minute=mm, second=0, microsecond=0)
        t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        return t

    if args.date:
        raise SystemExit("错误：--date 必须与 --at HH:MM 一起使用（仅给日期无法确定时刻）")

    if args.after is not None:
        return now + timedelta(minutes=args.after)

    # 旧行为：启动次日 03:00
    return (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)


def trigger_shutdown(reason):
    log(f"触发关机：{reason}")
    cmd = ["shutdown", "/s", "/t", "60",
           "/c", f"继续教育学习完毕，自动关机（{reason}）。如需取消请在 60 秒内执行 shutdown /a"]
    log("执行命令: " + " ".join(cmd))
    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        log(f"shutdown 调用失败: {e}")
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="继续教育刷课自动关机看门狗")
    ap.add_argument("--at", metavar="HH:MM | 'YYYY-MM-DD HH:MM'",
                    help="关机时刻（只给 HH:MM 时：今天；已过则顺延明天）")
    ap.add_argument("--date", metavar="YYYY-MM-DD", help="与 --at HH:MM 搭配，指定具体日期")
    ap.add_argument("--after", type=int, metavar="MIN", help="多少分钟后关机")
    ap.add_argument("--on-all-done", action="store_true",
                    help="仅当所有课程真正刷完（completed/all_courses_done/done_no_more_courses 或学分达标）时提前关机")
    ap.add_argument("--on-study-done", action="store_true",
                    help="本次刷课会话结束（含 time_up 计时到点）时提前关机")
    args = ap.parse_args()

    explicit_time = bool(args.at) or (args.after is not None) or bool(args.date)

    # 决定"提前关机"的条件集合
    if args.on_all_done:
        use_study_done, done_statuses, done_label = True, ALL_DONE_STATUSES, "全部课程刷完"
    elif args.on_study_done:
        use_study_done, done_statuses, done_label = True, SESSION_END_STATUSES, "本次会话结束"
    elif explicit_time:
        # 只按时间关机（旧语义，保持兼容）
        use_study_done, done_statuses, done_label = False, SESSION_END_STATUSES, "（未启用）"
    else:
        # 无参数：旧行为
        use_study_done, done_statuses, done_label = True, SESSION_END_STATUSES, "本次会话结束"

    target = parse_target(args)
    now = datetime.now()

    log("=== 自动关机看门狗启动 ===")
    log(f"当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"目标关机时间：{target.strftime('%Y-%m-%d %H:%M:%S')}"
        f"（约 {(target - now).total_seconds() / 3600:.1f} 小时后）")
    log("判定规则：")
    if use_study_done:
        log(f"  ① 刷课 {done_label}（status ∈ {sorted(done_statuses)}）→ 立即关机")
    log(f"  {'②' if use_study_done else '①'} 当前时间 ≥ {target.strftime('%Y-%m-%d %H:%M')} → 关机")
    log("缓冲：60 秒（用户可执行 shutdown /a 取消）")
    log("")

    iteration = 0
    while True:
        iteration += 1
        # 条件 1：刷课完成（仅在启用时）。status 判定 + 学分达标判定，任一满足即关机
        if use_study_done:
            done, reason = check_study_done(done_statuses)
            if not done:
                cdone, creason = check_credit_done()
                if cdone:
                    done, reason = True, creason
            if done:
                log(f"第 {iteration} 次检查：刷课已完成（{reason}）")
                if trigger_shutdown(f"刷课已完成 ({reason})"):
                    return 0
        # 条件 2：到达目标时间
        if datetime.now() >= target:
            log(f"第 {iteration} 次检查：到达目标时间（{target.strftime('%Y-%m-%d %H:%M')}）")
            if trigger_shutdown(f"到达目标时间 {target.strftime('%Y-%m-%d %H:%M')}"):
                return 0

        if iteration % 10 == 1:
            remain = target - datetime.now()
            hrs = int(remain.total_seconds() // 3600)
            mins = int((remain.total_seconds() % 3600) // 60)
            log(f"第 {iteration} 次检查：未到点，距关机 {hrs}h{mins}min")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("用户中断（Ctrl+C），退出看门狗")
        sys.exit(0)
