# -*- coding: utf-8 -*-
"""
继续教育【远程扫码登录】脚本。
用途：人不在电脑前时，脚本打开浙江政务服务网登录页 → 切到「扫码登录」→
      把二维码截图保存到本地固定路径（供 WorkBuddy 手机 App 查看），
      循环刷新二维码、检测登录成功，成功后保存登录态 jxjy_state.json。

用法：
  python jxjy_remote_login.py          # 完整模式：循环截图+刷新二维码+等登录
  python jxjy_remote_login.py --demo   # 演示模式：只截一次二维码就退出（验证用）
  python jxjy_remote_login.py --wait N # 最多等 N 分钟（默认 10）

配合 WorkBuddy 手机 App 的使用流程（见脚本末尾说明）。
"""
import os, sys, json, time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header

from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "jxjy_state.json")
MAIL_CONFIG = os.path.join(BASE, "jxjy_mail_config.json")
FLAG_FILE = os.path.join(BASE, "jxjy_login_success.flag")
QR_FILE = os.path.join(BASE, "jxjy_login_qr.png")
QR_META = os.path.join(BASE, "jxjy_login_qr.meta.txt")  # 每次截图写一行时间戳

JXJY_HOME = "https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html"

DEMO = "--demo" in sys.argv
MAX_WAIT = 10 * 60
for _i, _a in enumerate(sys.argv):
    if _a == "--wait" and _i + 1 < len(sys.argv):
        try:
            MAX_WAIT = int(sys.argv[_i + 1]) * 60
        except ValueError:
            pass


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def load_mail_config():
    """读取邮件配置；不存在或字段缺失返回 None。"""
    if not os.path.exists(MAIL_CONFIG):
        return None
    try:
        with open(MAIL_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("from_addr") and cfg.get("pass") and cfg.get("to_addr"):
            return cfg
    except Exception:
        pass
    return None


def send_qr_email(qr_path):
    """把二维码图片作为附件发到用户邮箱。返回 (成功, 描述)。"""
    cfg = load_mail_config()
    if cfg is None:
        return False, "无邮件配置"
    try:
        msg = MIMEMultipart()
        msg["From"] = cfg["from_addr"]
        msg["To"] = cfg["to_addr"]
        msg["Subject"] = Header("继续教育登录二维码", "utf-8")
        body = ("这是浙江会计继续教育的登录二维码。\n\n"
                "请把附件图片保存到手机相册，然后用「浙里办」或「支付宝」或「微信」的"
                "扫一扫 → 从相册选图，完成登录。\n\n"
                "（二维码约 2 分钟有效，若已过期请等待下一封邮件或联系助手刷新。）")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with open(qr_path, "rb") as f:
            img = MIMEImage(f.read())
        img.add_header("Content-Disposition", "attachment", filename="login_qr.png")
        msg.attach(img)

        host = cfg.get("smtp_host", "smtp.qq.com")
        port = int(cfg.get("smtp_port", 465))
        server = smtplib.SMTP_SSL(host, port, timeout=30)
        server.login(cfg["from_addr"], cfg["pass"])
        server.sendmail(cfg["from_addr"], [cfg["to_addr"]], msg.as_string())
        server.quit()
        return True, "已发送到 %s" % cfg["to_addr"]
    except Exception as e:
        return False, "发送失败: %s" % e


def login_indicator(ctx):
    """返回 (是否已登录进入学习中心, 描述)。"""
    try:
        cookies = ctx.cookies()
        names = {c["name"] for c in cookies}
        has_sso = "SSO_TOKEN" in names or "zjzwfwlogin" in names
        on_study = False
        urls = []
        for pg in ctx.pages:
            try:
                u = pg.url
                urls.append(u[:70])
                if "jxjy.czt.zj.gov.cn" in u and "/front/" in u and "login" not in u and "ticket" not in u:
                    on_study = True
                if "learncenter" in u or "golearncenter" in u:
                    on_study = True
            except Exception:
                pass
        return (has_sso and on_study), "has_sso=%s on_study=%s urls=%s" % (has_sso, on_study, urls)
    except Exception as e:
        return False, "err=%s" % e


def click_qr_tab(page):
    """切换到「扫码登录」tab，返回是否成功。"""
    for sel in ['text=扫码登录', 'div:has-text("扫码登录")', 'span:has-text("扫码登录")',
                'a:has-text("扫码登录")', 'li:has-text("扫码登录")']:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=4000)
                log("已点击扫码登录 tab: %s" % sel)
                return True
        except Exception:
            continue
    return False


def find_qr_canvas(page):
    """找到二维码 canvas（可见且边长 >= 120px）。"""
    best = None
    try:
        for i in range(page.locator("canvas").count()):
            c = page.locator("canvas").nth(i)
            if not c.is_visible():
                continue
            box = c.bounding_box()
            if box and box["width"] >= 120 and box["height"] >= 120:
                best = c
                break
    except Exception:
        pass
    return best


def save_qr(page):
    """截取二维码保存到 QR_FILE，返回是否成功。"""
    canvas = find_qr_canvas(page)
    if canvas is None:
        return False
    try:
        canvas.screenshot(path=QR_FILE)
        with open(QR_META, "a", encoding="utf-8") as f:
            f.write("%s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        log("二维码已保存 -> %s" % QR_FILE)
        if not DEMO:
            ok, desc = send_qr_email(QR_FILE)
            log("邮件推送：%s" % desc)
        return True
    except Exception as e:
        log("截图失败: %s" % e)
        return False


def qr_expired(page):
    """检测二维码是否已失效。"""
    try:
        body = page.inner_text("body")[:2000]
        for kw in ["已失效", "已过期", "二维码失效", "重新获取", "点击刷新", "刷新二维码"]:
            if kw in body:
                return True
    except Exception:
        pass
    return False


def try_refresh_qr(page):
    """二维码失效后尝试点击刷新。"""
    for sel in ['text=刷新', 'text=重新获取', 'text=点击刷新', 'a:has-text("刷新")',
                'div:has-text("刷新")', 'img[alt*="刷新"]']:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=3000)
                log("点击刷新二维码: %s" % sel)
                time.sleep(2)
                return True
        except Exception:
            continue
    return False


def main():
    os.makedirs(BASE, exist_ok=True)
    with sync_playwright() as p:
        # 用独立临时 profile（避免和正在跑的刷课任务冲突）
        ctx = p.chromium.launch_persistent_context(
            os.path.join(BASE, "jxjy_remote_profile"),
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=["--no-first-run", "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(JXJY_HOME, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)

        # 若已在学习中心（无需登录），直接结束
        logged, desc = login_indicator(ctx)
        if logged:
            log("已处于登录状态，无需扫码。%s" % desc)
            ctx.storage_state(path=STATE_FILE)
            open(FLAG_FILE, "w").write("ok")
            ctx.close()
            return

        # 切到扫码登录
        if not click_qr_tab(page):
            log("[!] 未找到「扫码登录」入口，当前页面文本：")
            try:
                print(page.inner_text("body")[:600], flush=True)
            except Exception:
                pass
        time.sleep(4)

        ok = save_qr(page)
        if not ok:
            log("[!] 未截到二维码 canvas，尝试整页截图兜底")
            try:
                page.screenshot(path=QR_FILE)
                log("已整页截图兜底 -> %s" % QR_FILE)
                ok = True
            except Exception as e:
                log("整页截图也失败: %s" % e)

        if DEMO:
            log("[demo] 演示模式结束，二维码已保存到 %s" % QR_FILE)
            time.sleep(2)
            ctx.close()
            return

        log("[*] 已进入远程扫码等待。请在 WorkBuddy 手机 App 中查看二维码并用浙里办/支付宝/微信扫码。")
        t0 = time.time()
        last_qr = time.time()
        while time.time() - t0 < MAX_WAIT:
            time.sleep(4)
            logged, desc = login_indicator(ctx)
            # 检测登录成功
            if logged:
                time.sleep(5)
                ctx.storage_state(path=STATE_FILE)
                open(FLAG_FILE, "w").write("ok")
                log("[OK] LOGIN_SUCCESS 登录态已保存 -> %s" % STATE_FILE)
                ctx.close()
                return
            # 二维码失效则刷新，否则每 45 秒重截一次（覆盖同名文件）
            if qr_expired(page):
                log("[*] 检测到二维码失效，尝试刷新")
                try_refresh_qr(page)
                time.sleep(3)
                save_qr(page)
                last_qr = time.time()
            elif time.time() - last_qr > 45:
                save_qr(page)
                last_qr = time.time()
        log("[!] 等待超时，未检测到登录成功")
        ctx.close()


if __name__ == "__main__":
    main()
