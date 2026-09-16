# -*- coding: utf-8 -*-
"""
一键闭环：从登录跑到 90 学分 → 下载学习证明 → 生成结算报告 → 过目后清理 → 复位待下一年度

用法：
  python jxjy_full_run.py                     # 交互式，默认每轮 480 分钟、最多 20 轮
  python jxjy_full_run.py --minutes 240       # 自定义单轮时长
  python jxjy_full_run.py --rounds 3          # 限制轮数
  python jxjy_full_run.py --yes               # 无人值守：结算后直接清理，不再等你确认
  python jxjy_full_run.py --no-cert           # 跳过拉证
  python jxjy_full_run.py --status            # 只看当前进度，不刷课

闭环设计的三条硬约束：
  1. 未达标就绝不清理 —— 清理的唯一入口是先确认学分达标且证明已落盘
  2. 清理保留 config 与登录态 —— 下一年直接跑，不用重新配一遍
  3. 默认要你过目 —— --yes 才跳过确认
"""
import os
import sys
import json
import time
import shutil
import argparse
import datetime
import subprocess

import jxjy_conf as CONF

BASE = CONF.BASE
STATE_FILE = os.path.join(BASE, "jxjy_state.json")
DASH_FILE = os.path.join(BASE, "jxjy_dashboard_data.json")
REPORT_FILE = os.path.join(BASE, "jxjy_study_report.json")
FINAL_FILE = os.path.join(BASE, "jxjy_final_report.json")
LOG_FILE = os.path.join(BASE, "jxjy_full_run.log")
PROOF_DIR = os.path.join(os.path.dirname(BASE), "继续教育证明")

SCRIPTS = {
    "study": os.path.join(BASE, "jxjy_daily_study.py"),
    "login": os.path.join(BASE, "jxjy_login_window.py"),
    "cert": os.path.join(BASE, "jxjy_download_cert.py"),
    "refresh": os.path.join(BASE, "refresh_jxjy_after_session.py"),
}

TEMP_FILES = [
    "jxjy_study.lock",
    "jxjy_login_success.flag",
    "jxjy_login_qr.png",
]

ARCHIVE_KEEP = [
    "jxjy_study.log",
    "jxjy_full_run.log",
    "jxjy_study_report.json",
    "jxjy_final_report.json",
    "jxjy_dashboard_data.json",
    "jxjy_after_session.log",
    "jxjy_download_cert_chain.log",
    "jxjy_login_window_chain.log",
    "jxjy_login_window.log",
    "jxjy_chain.log",
]

PY = sys.executable

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(msg, quiet=False):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    if not quiet:
        print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] {msg}\n")
    except Exception:
        pass


def read_dashboard():
    if not os.path.exists(DASH_FILE):
        return None
    try:
        with open(DASH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def read_report():
    if not os.path.exists(REPORT_FILE):
        return {}
    try:
        with open(REPORT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def judge(dash=None):
    """判定是否达标。返回 (是否达标, 描述, 明细)。"""
    d = dash or read_dashboard()
    if not d:
        return False, "尚无学分数据", {}

    got_t = float(d.get("total", {}).get("got", 0) or 0)
    got_m = float(d.get("major", {}).get("got", 0) or 0)
    got_p = float(d.get("public", {}).get("got", 0) or 0)
    need_t = CONF.credit_total()
    need_m = CONF.credit_major()
    need_p = CONF.credit_public()

    detail = {
        "total": {"got": got_t, "need": need_t},
        "major": {"got": got_m, "need": need_m},
        "public": {"got": got_p, "need": need_p},
        "student": d.get("student"),
        "updated_at": d.get("updated_at"),
    }
    ok = got_t >= need_t - 0.001 and got_m >= need_m - 0.001 and got_p >= need_p - 0.001
    desc = f"总{got_t}/{need_t} 专业{got_m}/{need_m} 公需{got_p}/{need_p}"
    return ok, desc, detail


def run_script(path, args, desc):
    """以子进程跑一段，实时输出。返回退出码。"""
    if not os.path.exists(path):
        log(f"[缺失] {os.path.basename(path)} 不存在，跳过「{desc}」")
        return -1
    cmd = [PY, "-u", path] + [str(a) for a in args]
    log(f"启动 {desc}: {' '.join(cmd[2:])}")
    try:
        return subprocess.call(cmd, cwd=BASE)
    except KeyboardInterrupt:
        log("被 Ctrl+C 中断")
        return 130
    except Exception as e:
        log(f"启动失败: {e}")
        return -1


def ensure_login(wait_min):
    """登录态缺失时走登录窗口。返回是否可用。"""
    if os.path.exists(STATE_FILE):
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(STATE_FILE))
        age_h = (datetime.datetime.now() - mt).total_seconds() / 3600
        if age_h < 9:
            log(f"登录态有效（{age_h:.1f} 小时前刷新）")
            return True
        log(f"登录态已过 {age_h:.1f} 小时，接近失效边界")
    else:
        log("未找到登录态")

    print()
    print("  需要扫码登录一次（浙里办 / 浙江政务服务网）。")
    print(f"  即将弹出浏览器窗口，最长等待 {wait_min} 分钟。")
    if sys.stdin and sys.stdin.isatty():
        try:
            if input("  回车开始，Ctrl+C 取消 > ").strip().lower() in ("n", "no", "取消"):
                return False
        except EOFError:
            pass
    return run_script(SCRIPTS["login"], ["--wait", wait_min], "登录窗口") == 0


def latest_proof():
    """找最近一次下载的证明文件。PDF 优先于 JPG/XML（同一批三者同时落盘，
    直接取 mtime 最大的话常常挑到 xml，展示和交付都不直观）。"""
    cands = []
    for d in (PROOF_DIR, os.path.dirname(BASE), BASE):
        if not os.path.isdir(d):
            continue
        for n in os.listdir(d):
            if n.startswith("继续教育学习证明") and n.lower().endswith((".pdf", ".jpg", ".jpeg", ".xml")):
                cands.append(os.path.join(d, n))
    if not cands:
        return None
    rank = {".pdf": 0, ".jpg": 1, ".jpeg": 1, ".xml": 2}

    def key(p):
        ext = os.path.splitext(p)[1].lower()
        return (rank.get(ext, 9), -os.path.getmtime(p))

    return min(cands, key=key)


def write_final(detail, rounds, elapsed, cert_path, cert_rc):
    ok, desc, _ = judge()
    data = {
        "finished_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "year": CONF.year(),
        "province": CONF.load()["province"],
        "rounds": rounds,
        "elapsed_seconds": int(elapsed),
        "credit_detail": detail,
        "reached": ok,
        "summary": desc,
        "cert_downloaded": bool(cert_path),
        "cert_path": cert_path,
        "cert_exit_code": cert_rc,
        "config_file": CONF.CONFIG_FILE,
        "state_file": STATE_FILE,
    }
    with open(FINAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def cleanup(year, keep_state=True):
    """归档本轮产物、清掉临时文件。保留 config、登录态、证书。"""
    arch = os.path.join(BASE, "jxjy_archive", str(year))
    os.makedirs(arch, exist_ok=True)
    moved, removed = [], []

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    for n in ARCHIVE_KEEP:
        p = os.path.join(BASE, n)
        if os.path.exists(p):
            dst = os.path.join(arch, f"{stamp}_{n}")
            shutil.move(p, dst)
            moved.append(n)

    for pat in ["jxjy_fail_*.png", "jxjy_login_qr.png"]:
        import glob
        for p in glob.glob(os.path.join(BASE, pat)):
            os.remove(p)
            removed.append(os.path.basename(p))

    for n in TEMP_FILES:
        p = os.path.join(BASE, n)
        if os.path.exists(p):
            os.remove(p)
            removed.append(n)

    if not keep_state and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        removed.append("jxjy_state.json")

    log(f"已归档 {len(moved)} 个文件到 jxjy_archive/{year}/，清理临时文件 {len(removed)} 个")
    log(f"保留：{os.path.basename(CONF.CONFIG_FILE)}、登录态、继续教育证明/")
    return moved, removed


def print_status():
    ok, desc, detail = judge()
    print("\n=== 当前进度 ===")
    print("  " + CONF.summary())
    print(f"  {desc} -> {'已达标 ✅' if ok else '未达标'}")
    d = read_report()
    if d.get("status"):
        print(f"  上次刷课状态: {d.get('status')}")
    proof = latest_proof()
    print(f"  学习证明: {proof or '尚未下载'}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=None)
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--yes", "-y", action="store_true")
    ap.add_argument("--no-cert", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--cleanup-only", action="store_true")
    a = ap.parse_args()

    if a.status:
        return print_status()

    cfg = CONF.load()
    year = CONF.year()
    minutes = a.minutes or cfg["study"]["max_minutes_per_run"]
    t0 = time.time()

    log("=" * 50)
    log(f"闭环启动 | {CONF.summary()}")
    log(f"单轮 {minutes} 分钟，最多 {a.rounds} 轮")

    if not os.path.exists(CONF.CONFIG_FILE):
        print()
        print("  ⚠️  没有配置文件 jxjy_config.json，当前使用内置默认值。")
        print("     想自定义年度/学分/时长，先跑：python jxjy_setup.py")

    if a.cleanup_only:
        ok, desc, _ = judge()
        if not ok and not a.yes:
            print(f"  当前 {desc}，未达标，拒绝清理。")
            return 1
        cleanup(year)
        return 0

    # ── 阶段 1：登录 ──────────────────────────────────
    if not ensure_login(cfg["study"]["login_wait_minutes"]):
        log("登录未完成，闭环中止（未达标，不做任何清理）")
        return 1

    # ── 阶段 2：刷课循环，直到达标或轮数用尽 ──────────
    ok, desc, detail = False, "", {}
    rounds = 0
    for i in range(1, a.rounds + 1):
        rounds = i
        ok, desc, _pre = judge()
        if ok:
            log(f"开轮前判定已达标：{desc}")
            break
        log(f"—— 第 {i}/{a.rounds} 轮 ——")
        run_script(SCRIPTS["study"], [minutes], f"第{i}轮刷课")

        rep = read_report()
        st = rep.get("status")
        # 刷新一次学分，报告里的学分面板可能滞后
        if os.path.exists(SCRIPTS["refresh"]):
            subprocess.call([PY, "-u", SCRIPTS["refresh"]], cwd=BASE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        ok, desc, detail = judge()
        log(f"本轮结束学分：{desc}")

        if ok:
            log("🎉 年度学分已全部达标")
            break
        if st == "error":
            log("刷课脚本报错（多半是登录态失效），尝试重新登录一次")
            if not ensure_login(cfg["study"]["login_wait_minutes"]):
                log("重登失败，闭环中止（未达标，不做任何清理）")
                return 1
        if st in ("done_no_more_courses", "too_many_entry_failures"):
            log(f"刷课脚本返回 {st}：暂无可刷课程，停止多轮循环")
            break

    elapsed = time.time() - t0

    if not ok:
        log(f"轮次用尽仍未达标：{desc}")
        print()
        print("  本轮未刷满，已保留全部中间数据，下次继续即可，不会丢进度。")
        print("  想换个时段再跑：python jxjy_full_run.py")
        write_final(detail, rounds, elapsed, None, None)
        return 1

    # ── 阶段 3：拉学习证明 ────────────────────────────
    cert_path, cert_rc = None, None
    if not a.no_cert and cfg["finish"]["download_cert"]:
        before = set()
        for d in (PROOF_DIR, os.path.dirname(BASE)):
            if os.path.isdir(d):
                before |= {os.path.join(d, n) for n in os.listdir(d)}
        cert_rc = run_script(SCRIPTS["cert"], [cfg["study"]["cert_wait_minutes"]], "下载学习证明")
        p = latest_proof()
        if p and p not in before:
            cert_path = p
        elif p:
            cert_path = p
        if cert_rc == 0 and cert_path:
            log(f"学习证明已下载：{cert_path}")
        else:
            log(f"学习证明未拿到（退出码 {cert_rc}；0成功 2登录失效 3超时 4找不到入口）")

    final = write_final(detail, rounds, elapsed, cert_path, cert_rc)

    # ── 阶段 4：结算报告 + 过目 ───────────────────────
    print()
    print("=" * 56)
    print(f"  {year} 年度学习结算")
    print("=" * 56)
    if detail.get("student"):
        print(f"  学员：{detail['student']}")
    print(f"  学分：{final['summary']}")
    need_t = detail.get("total", {}).get("need")
    got_t = detail.get("total", {}).get("got")
    print(f"  板块：专业课 {detail.get('major',{}).get('got')}/{detail.get('major',{}).get('need')}"
          f"　公需课 {detail.get('public',{}).get('got')}/{detail.get('public',{}).get('need')}")
    print(f"  轮次：{rounds} 轮，累计 {elapsed/60:.0f} 分钟")
    print(f"  证明：{cert_path or '未下载'}")
    print(f"  报告：{FINAL_FILE}")
    print("=" * 56)

    # ── 阶段 5：确认后清理 ────────────────────────────
    do_cleanup = False
    if a.yes or cfg["finish"]["auto_cleanup"]:
        do_cleanup = True
        log("配置为自动清理，跳过确认")
    else:
        print()
        try:
            ans = input("  核对无误请输入 y 清理并复位（其他键保留现场）> ").strip().lower()
            do_cleanup = ans in ("y", "yes", "是")
        except EOFError:
            log("非交互环境，保留现场")

    if do_cleanup:
        cleanup(year, keep_state=True)
        print()
        print("  已清理。配置与登录态保留，下一年度直接跑 jxjy_full_run.py 即可。")
        if not cert_path:
            print("  ⚠️ 注意：本轮未下载到学习证明，建议手工去平台确认后再归档。")
    else:
        print("  已保留现场，随时可重跑或手工归档。")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中断（未做任何清理）")
        sys.exit(130)
