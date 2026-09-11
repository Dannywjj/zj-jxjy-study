# -*- coding: utf-8 -*-
"""继续教育 · 登录态守护 + 会话接力看门狗

背景（为什么要这个脚本）：
  浙里办 SSO 会话有效期很短（实测 < 9 小时），跨天长时间刷课中途必然掉线。
  掉线后刷课脚本会以 status="error" 退出，此时如果没人发现，会白等几个小时。
  本守护把"发现 → 通知 → 恢复 → 接力"这条链路自动化：

  巡检（默认每 3 分钟）：
    1. 读 jxjy_study.lock 的 PID 判断刷课进程是否存活
    2. 若进程已死：
       a. report.status ∈ {all_courses_done, completed, done_no_more_courses} → 全部刷完，守护退出
       b. report.status == "error" 且错误信息含 zjzwfw/登录特征 → 登录态失效 → 走救援
       c. 其他（time_up / running / 崩溃）→ 直接接力重启会话
    3. 若进程存活但 jxjy_study.log 超过 --hang-min 分钟没有更新 → 视为卡死，杀进程树后接力

  退避（防止系统性故障时疯狂拉起浏览器、被平台风控盯上）：
    连续接力失败 → 前两次立即重试，之后 5/15/30/60 分钟逐级放大；
    一旦观察到"会话存活且日志 5 分钟内有更新"，计数立即清零（正常长跑接力不受影响）。
    登录救援失败不走这条退避，而是按 --retry-min（默认 10 分钟）固定节流 ——
    那是"等人工扫码"的正常等待，不是故障。

  救援（登录态失效时）：
    · 调 jxjy_remote_login.py：打开扫码页 → 把二维码邮件推给用户 → 等待扫码
      先无头模式（实测锁屏/无人值守也能截到二维码），失败再退化为有头窗口兜底
      （若持久化 profile 恰好仍在线，该脚本会直接静默续期，无需人工）
    · 扫码成功后自动重启刷课会话，时长 = 距 --session-end 的剩余分钟数
    · 失败则按 --retry-min 节流后下一轮再试

用法：
  python jxjy_login_guard.py                     # 旧行为：守到启动次日 03:00
  python jxjy_login_guard.py --until "2026-09-12 21:00" --session-end "2026-09-12 20:45"
  python jxjy_login_guard.py --status            # 只打印一次当前状态，不守护
  python jxjy_login_guard.py --dry-run --until ... # 只记录将要做的动作，不真的执行
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable or "python"

LOCK_FILE = os.path.join(BASE, "jxjy_study.lock")
REPORT_FILE = os.path.join(BASE, "jxjy_study_report.json")
STATE_FILE = os.path.join(BASE, "jxjy_state.json")
STUDY_LOG = os.path.join(BASE, "jxjy_study.log")
GUARD_LOG = os.path.join(BASE, "jxjy_login_guard.log")
STUDY_SCRIPT = os.path.join(BASE, "jxjy_daily_study.py")
REMOTE_LOGIN = os.path.join(BASE, "jxjy_remote_login.py")

# 真正"全部刷完"的完成态（与看门狗 ALL_DONE_STATUSES 保持一致）
DONE_STATUSES = {"all_courses_done", "completed", "done_no_more_courses"}
# 登录态失效的特征
LOGIN_HINTS = ("zjzwfw.gov.cn", "未能进入学习中心", "ssoLogin", "请先运行 jxjy_login_window")

CHECK_INTERVAL = 180          # 巡检间隔（秒）
HANG_MINUTES = 20             # 日志静默超过该分钟数视为卡死
RETRY_MINUTES = 10            # 救援失败的节流间隔（分钟）
MIN_SESSION_MIN = 10          # 剩余时间不足该分钟数时不再接力
# 连续接力失败后的退避（分钟）：第 1/2 次立即重试，之后逐级放大，避免系统性故障时
# 每 3 分钟就拉起一个浏览器、把平台风控刷出来
BACKOFF_MINUTES = [0, 0, 5, 15, 30, 60]
HEALTHY_RESET_SECONDS = 300   # 会话存活且日志 5 分钟内有更新 → 视为恢复正常，退避清零


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(GUARD_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- 基础探测

def _pid_alive(pid):
    """Windows 下判断进程是否存活（tasklist 中文输出为 GBK，用 errors=replace 兜底）"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10
        ).stdout
        return str(pid) in out
    except Exception:
        return False


def study_pid():
    """读单实例锁里的 PID；无锁返回 None"""
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            pid = int((f.read() or "").strip())
        return pid
    except Exception:
        return None


def study_running():
    pid = study_pid()
    if pid and _pid_alive(pid):
        return True, pid
    return False, pid


def read_report():
    try:
        with open(REPORT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def study_log_age_min():
    """jxjy_study.log 距上次写入的分钟数；文件不存在返回 9999"""
    if not os.path.exists(STUDY_LOG):
        return 9999
    return (time.time() - os.path.getmtime(STUDY_LOG)) / 60.0


def report_age_min():
    """jxjy_study_report.json 距上次写入的分钟数；文件不存在返回 9999"""
    if not os.path.exists(REPORT_FILE):
        return 9999
    return (time.time() - os.path.getmtime(REPORT_FILE)) / 60.0


def is_login_failure(report, max_age_min=60):
    """报告是否为"登录态失效"中断。

    只认 60 分钟内写过的报告：进程被强杀时报告不会刷新，
    否则会拿上一次的旧登录错误报告误判、白白推送二维码。
    """
    if report.get("status") != "error":
        return False
    if report_age_min() > max_age_min:
        return False
    blob = json.dumps(report, ensure_ascii=False)
    return any(h in blob for h in LOGIN_HINTS)


# ---------------------------------------------------------------- 动作

def kill_study_tree(pid, dry_run=False):
    """杀掉刷课进程树（含 playwright 子进程）"""
    log(f"  杀进程树 PID {pid}" + ("（dry-run 跳过）" if dry_run else ""))
    if dry_run:
        return
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=20)
    except Exception as e:
        log(f"  taskkill 失败: {e}")


def _state_mtime():
    return os.path.getmtime(STATE_FILE) if os.path.exists(STATE_FILE) else 0


def _run_remote_login(extra_args, wait_min, label, dry_run):
    """跑一次远程登录脚本；返回登录态是否被刷新"""
    log(f"  [{label}] 拉起远程扫码登录（最多等 {wait_min} 分钟，二维码会邮件推送）"
        + ("（dry-run 跳过）" if dry_run else ""))
    if dry_run:
        return False
    before = _state_mtime()
    try:
        subprocess.run([PY, REMOTE_LOGIN] + extra_args + ["--wait", str(wait_min)],
                       cwd=BASE, timeout=wait_min * 60 + 180)
    except subprocess.TimeoutExpired:
        log(f"  [{label}] 远程登录脚本超时")
    except Exception as e:
        log(f"  [{label}] 远程登录脚本异常: {e}")
    return _state_mtime() > before


def remote_login(wait_min, dry_run=False):
    """推送二维码并等待扫码；成功（jxjy_state.json 被刷新）返回 True。

    先无头模式：2026-09-11 实测无头也能正常切到「扫码登录」tab 并截到二维码，
    因此**锁屏 / 无人值守时同样可用**（有头窗口在锁屏会话上可能渲染失败）。
    无头未成功再退化为有头窗口兜底。
    """
    if _run_remote_login(["--headless"], wait_min, "无头", dry_run):
        log("  登录态已刷新（无头模式）")
        return True
    if _run_remote_login([], wait_min, "有头兜底", dry_run):
        log("  登录态已刷新（有头兜底）")
        return True
    log("  登录态未刷新（无人扫码或扫码失败）")
    return False


def launch_study(minutes, reason, dry_run=False):
    """后台重启刷课会话"""
    log(f"  接力启动刷课会话：{minutes} 分钟（{reason}）" + ("（dry-run 跳过）" if dry_run else ""))
    if dry_run:
        return True
    try:
        f = open(STUDY_LOG, "a", encoding="utf-8")
        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([PY, STUDY_SCRIPT, str(minutes)], cwd=BASE,
                         stdout=f, stderr=subprocess.STDOUT,
                         creationflags=flags, close_fds=True)
        log("  已发出启动指令（新进程会自行获取单实例锁）")
        return True
    except Exception as e:
        log(f"  启动失败: {e}")
        return False


def remaining_minutes(session_end):
    return int((session_end - datetime.now()).total_seconds() // 60)


def apply_backoff(streak, dry_run=False):
    """连续接力失败的退避：必要时先等一会儿，返回 +1 后的 streak。

    前两次立即重试，之后 5/15/30/60 分钟逐级放大。
    会话恢复正常（存活且日志新鲜）时会清零，因此不影响正常的长跑接力。
    """
    wait_s = BACKOFF_MINUTES[min(streak, len(BACKOFF_MINUTES) - 1)] * 60
    if wait_s:
        log(f"  连续第 {streak} 次接力仍失败，退避 {wait_s // 60} 分钟后重试")
        if not dry_run:
            time.sleep(wait_s)
    return streak + 1


# ---------------------------------------------------------------- 状态打印

def print_status():
    running, pid = study_running()
    rep = read_report()
    print("刷课进程：%s%s" % ("运行中" if running else "未运行",
                            f"（PID {pid}）" if running else ""))
    print("最近报告：status=%s，时间=%s（%.1f 分钟前写入）"
          % (rep.get("status"), rep.get("date"), report_age_min()))
    if rep.get("error"):
        print("报告错误：%s" % str(rep["error"])[:160])
    print("学习日志：%.1f 分钟前有写入" % study_log_age_min())
    print("登录态文件：%s" % (
        datetime.fromtimestamp(os.path.getmtime(STATE_FILE)).strftime("%Y-%m-%d %H:%M:%S")
        if os.path.exists(STATE_FILE) else "缺失"))
    print("是否登录态失效：%s" % is_login_failure(rep))


# ---------------------------------------------------------------- 主循环

def main():
    ap = argparse.ArgumentParser(description="继续教育登录态守护 + 会话接力看门狗")
    ap.add_argument("--until", metavar="'YYYY-MM-DD HH:MM' | HH:MM",
                    help="守护截止时间（到点后守护退出）；不填 = 启动次日 03:00")
    ap.add_argument("--session-end", metavar="'YYYY-MM-DD HH:MM'",
                    help="刷课会话自然结束时间；接力时按距此时间的剩余分钟数启动")
    ap.add_argument("--interval", type=int, default=CHECK_INTERVAL, help="巡检间隔秒数")
    ap.add_argument("--hang-min", type=int, default=HANG_MINUTES, help="日志静默多少分钟视为卡死")
    ap.add_argument("--retry-min", type=int, default=RETRY_MINUTES, help="救援失败后的重试间隔（分钟）")
    ap.add_argument("--wait-min", type=int, default=15,
                    help="单次远程扫码等待分钟数（无头/有头各一次，最坏 2 倍）")
    ap.add_argument("--no-login-rescue", action="store_true", help="登录失效时只记录，不推送二维码")
    ap.add_argument("--no-hang-kill", action="store_true", help="卡死时只记录，不重启")
    ap.add_argument("--status", action="store_true", help="只打印当前状态后退出")
    ap.add_argument("--dry-run", action="store_true", help="只记录将要执行的动作")
    args = ap.parse_args()

    if args.status:
        print_status()
        return 0

    now = datetime.now()

    def parse_ts(text, fallback):
        if not text:
            return fallback
        text = text.strip().replace("T", " ")
        try:
            if " " in text:
                return datetime.strptime(text, "%Y-%m-%d %H:%M")
            hh, mm = (int(x) for x in text.split(":"))
            t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if t <= now:
                t += timedelta(days=1)
            return t
        except Exception as e:
            raise SystemExit(f"时间格式无法解析: {text!r} ({e})")

    until = parse_ts(args.until, (now + timedelta(days=1)).replace(
        hour=3, minute=0, second=0, microsecond=0))
    session_end = parse_ts(args.session_end, until)

    log("=== 继续教育登录态守护启动 ===")
    log(f"当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"守护截止：{until.strftime('%Y-%m-%d %H:%M:%S')}"
        f"（约 {(until - now).total_seconds() / 3600:.1f} 小时后）")
    log(f"会话终点：{session_end.strftime('%Y-%m-%d %H:%M:%S')}（接力时按剩余时间计算时长）")
    log(f"巡检间隔 {args.interval}s · 卡死阈值 {args.hang_min}min · 救援重试间隔 {args.retry_min}min")
    log(f"接力退避：连续失败按 {BACKOFF_MINUTES} 分钟逐级放大（会话恢复正常即清零）")
    log(f"救援顺序：先 --headless（锁屏可用）→ 失败再有头兜底，各 {args.wait_min} 分钟")
    if args.dry_run:
        log("注意：dry-run 模式，不会真的杀进程/推二维码/起会话")
    log("")

    last_rescue = 0.0
    fail_streak = 0
    iteration = 0

    while datetime.now() < until:
        iteration += 1
        running, pid = study_running()

        if running:
            age = study_log_age_min()
            # 会话活着且日志新鲜 → 说明接力成功/正常长跑，退避计数清零
            if fail_streak and age * 60 <= HEALTHY_RESET_SECONDS:
                log(f"  刷课会话已恢复正常（日志 {age:.1f} 分钟前更新），接力退避计数清零")
                fail_streak = 0
            if age > args.hang_min:
                log(f"第 {iteration} 次巡检：进程存活（PID {pid}）但日志已 {age:.0f} 分钟无更新 → 疑似卡死")
                if args.no_hang_kill:
                    log("  --no-hang-kill 已开启，仅记录不处理")
                else:
                    kill_study_tree(pid, args.dry_run)
                    time.sleep(5)
                    mins = remaining_minutes(session_end)
                    if mins >= MIN_SESSION_MIN:
                        fail_streak = apply_backoff(fail_streak, args.dry_run)
                        launch_study(mins, "卡死重启", args.dry_run)
                    else:
                        log(f"  剩余 {mins} 分钟不足 {MIN_SESSION_MIN} 分钟，不再接力")
            elif iteration % 10 == 1:
                log(f"第 {iteration} 次巡检：刷课进程正常运行（PID {pid}，日志 {age:.1f} 分钟前更新）")
            time.sleep(args.interval)
            continue

        # ---- 进程不在：判断原因 ----
        rep = read_report()
        status = rep.get("status")

        if status in DONE_STATUSES:
            log(f"第 {iteration} 次巡检：全部课程已刷完（status={status}），守护退出")
            return 0

        mins = remaining_minutes(session_end)
        if mins < MIN_SESSION_MIN:
            log(f"第 {iteration} 次巡检：距会话终点仅 {mins} 分钟，不再接力，守护退出")
            return 0

        if is_login_failure(rep):
            log(f"第 {iteration} 次巡检：刷课因【登录态失效】中断（{str(rep.get('error'))[:90]}）")
            now_ts = time.time()
            if now_ts - last_rescue < args.retry_min * 60:
                log(f"  距上次救援不足 {args.retry_min} 分钟，本轮跳过")
            elif args.no_login_rescue:
                log("  --no-login-rescue 已开启，仅记录不推送二维码")
            else:
                last_rescue = now_ts
                if remote_login(args.wait_min, args.dry_run):
                    launch_study(remaining_minutes(session_end), "登录恢复后接力", args.dry_run)
                else:
                    log(f"  救援未成功，{args.retry_min} 分钟后重试（期间可手动扫码，"
                        f"或运行 jxjy_login_window.py）")
        else:
            # time_up / running / 崩溃 等：直接接力（连续失败则逐级退避）
            log(f"第 {iteration} 次巡检：刷课进程已结束（status={status}），准备接力")
            fail_streak = apply_backoff(fail_streak, args.dry_run)
            launch_study(mins, f"会话结束接力（原 status={status}）", args.dry_run)

        time.sleep(args.interval)

    log("已到守护截止时间，守护退出")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("用户中断（Ctrl+C），守护退出")
        sys.exit(0)
