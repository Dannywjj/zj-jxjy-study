# -*- coding: utf-8 -*-
"""
继续教育登录窗口（一次性人工登录用）。
用系统 Chrome + 独立持久化 profile 打开 jxjy 页面，窗口稳定停留，
等待用户完成短信登录后自动检测登录态并保存。

用法：
  python jxjy_login_window.py          # 打开窗口并等待登录
  python jxjy_login_window.py --check  # 仅检测当前 profile 是否已登录（无头）
"""
import os, sys, json, time

from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(BASE, "jxjy_browser_profile")
STATE_FILE = os.path.join(BASE, "jxjy_state.json")
FLAG_FILE = os.path.join(BASE, "jxjy_login_success.flag")

JXJY_HOME = "https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html"
MAX_WAIT = 15 * 60  # 最多等 15 分钟，可用 --wait N 覆盖（单位分钟）
for _i, _a in enumerate(sys.argv):
    if _a == "--wait" and _i + 1 < len(sys.argv):
        try:
            MAX_WAIT = int(sys.argv[_i + 1]) * 60
        except ValueError:
            pass


def login_indicator(ctx):
    """返回 (是否已进入学习中心, 描述)。遍历所有页面 + 检查上下文 cookie。"""
    try:
        cookies = ctx.cookies()
        names = {c["name"] for c in cookies}
        has_sso = "SSO_TOKEN" in names or "zjzwfwlogin" in names
        urls = []
        on_study = False
        for pg in ctx.pages:
            try:
                u = pg.url
                urls.append(u[:70])
                # 学习中心特征：jxjy 域名 + front 路径，且不是登录页/ticket 中转页
                if "jxjy.czt.zj.gov.cn" in u and "/front/" in u and "login" not in u and "ticket" not in u:
                    on_study = True
                if "learncenter" in u or "golearncenter" in u:
                    on_study = True
            except Exception:
                pass
        return (has_sso and on_study), f"has_sso={has_sso} on_study={on_study} urls={urls}"
    except Exception as e:
        return False, f"err={e}"


def main():
    if "--check" in sys.argv:
        check_only()
        return

    os.makedirs(PROFILE, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE,
            headless=False,
            viewport=None,
            args=["--start-maximized", "--no-first-run", "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(JXJY_HOME, wait_until="domcontentloaded", timeout=60000)
        print("[*] 窗口已打开：%s" % JXJY_HOME, flush=True)
        print("[*] 页面会自动跳转到浙江政务服务网登录页，请在弹出的 Chrome 窗口中用短信登录。", flush=True)

        t0 = time.time()
        while time.time() - t0 < MAX_WAIT:
            time.sleep(3)
            logged, desc = login_indicator(ctx)
            print("[poll] %s" % desc, flush=True)
            if logged:
                # 再稳定等待几秒，确保会话 cookie 完全写盘
                time.sleep(6)
                ctx.storage_state(path=STATE_FILE)
                open(FLAG_FILE, "w").write("ok")
                print("[OK] LOGIN_SUCCESS 登录态已保存 -> %s" % STATE_FILE, flush=True)
                ctx.close()
                return
        print("[!] 超时，未检测到登录成功", flush=True)
        ctx.close()


def check_only():
    from playwright.sync_api import sync_playwright
    if not os.path.isdir(PROFILE):
        print("NOT_LOGGED_IN (无 profile)")
        return
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, headless=True)
        page = ctx.new_page()
        page.goto(JXJY_HOME, wait_until="domcontentloaded", timeout=60000)
        logged, desc = login_indicator(ctx)
        print("LOGGED_IN" if logged else "NOT_LOGGED_IN", desc)
        ctx.close()


if __name__ == "__main__":
    main()
