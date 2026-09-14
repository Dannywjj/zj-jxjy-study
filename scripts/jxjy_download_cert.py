#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jxjy_download_cert.py —— 浙江会计继续教育「学习证明」自动拉取

前置：
  1. 已完成登录（.workbuddy/jxjy_state.json 存在且 SSO 会话有效，< 9 小时）。
  2. 平台学分已达 90（总学分 >= 要求）。未达标时本脚本会在学习中心轮询等待，
     直到达标且出现「打印学习证明 / 学习证明 / 下载证明」按钮为止。

行为：
  - 复刻 jxjy_daily_study.py 进入学习中心的导航（含 4 次重试 + 首页兜底）。
  - 读取 2026 年度总学分；若 < 90 则每 60 秒复查（最多 wait 分钟）。
  - 达标后定位证明按钮，点击触发下载（PDF），保存到：
       继续教育证明/会计专业技术人员继续教育学习证明_YYYY-MM-DD.pdf
       并复制为 项目根/会计专业技术人员继续教育学习证明.pdf
  - 兼容两种下载方式：① 浏览器文件下载（expect_download）；② 新标签页 + 打印预览（page.pdf）。

用法：
  python jxjy_download_cert.py [wait_minutes]
      wait_minutes  达标前最多等待分钟数，默认 180（3 小时，配合登录窗口 <9h 用）
退出码：
  0  成功下载
  2  登录态失效（被踢到 user.zjzwfw.gov.cn）
  3  等待超时仍未达标
  4  达标但找不到证明按钮（已截图待人工辨识）
"""
import os
import sys
import time
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "jxjy_state.json")
ROOT = os.path.dirname(BASE)  # D:\图图\【图图小助理】
PROOF_DIR = os.path.join(ROOT, "继续教育证明")
TODAY = datetime.datetime.now().strftime("%Y-%m-%d")

CENTER_URL = "https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html"
HOME_URL = "https://jxjy.czt.zj.gov.cn/"

# 证明按钮候选文本（任一命中即点击）
PROOF_BTN_KEYWORDS = ["打印学习证明", "学习证明", "打印证明", "下载证明", "出具证明", "证明打印"]
# 宽泛兜底（避免出现精确文本时）
PROOF_BTN_FALLBACK = ["证明", "打印", "下载", "导出"]

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.info


def open_learning_center(page):
    """复刻 daily_study 进入学习中心：4 次重试 + 首页兜底。返回 page。"""
    for attempt in range(4):
        page.goto(CENTER_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        if "golearncenterNew" in page.url:
            break
        log(f"学习中心被重定向到 {page.url}，第 {attempt + 1} 次重试")
    if "user.zjzwfw.gov.cn" in page.url:
        raise RuntimeError("登录态失效：被重定向到政务网登录页")
    return page


def read_total_credit(page):
    """从学分总览表读取 2026 年度总学分（已获得）。返回 float 或 None。

    页面表格形如：
        年度    已获得学分   操作
        总学分  公需学分     专业学分
        2026    88.51       19.0  69.51  继续学习 查看详情
    年份行之后紧跟的三个数字依次为 总学分 / 公需学分 / 专业学分。
    """
    import re
    try:
        txt = page.evaluate("document.body.innerText")
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        # 学分行特征：含「查看详情」，且形如 2026 <总> <公需> <专业> …
        for line in lines:
            if "查看详情" in line:
                nums = re.findall(r"\d+\.\d+|\d+", line)
                # nums[0]=2026(年)，nums[1]=总学分
                if len(nums) >= 2:
                    return float(nums[1])
    except Exception as e:
        log(f"读取学分失败: {e}")
    return None


def find_proof_button(page):
    """在学习中心主框架查找证明按钮，返回 locator 或 None。"""
    from playwright.sync_api import TimeoutError as PWTimeout
    # 先精确
    for kw in PROOF_BTN_KEYWORDS:
        try:
            loc = page.locator(f'a:has-text("{kw}"), button:has-text("{kw}")').first
            if loc.count() and loc.is_visible(timeout=2000):
                return loc
        except Exception:
            pass
    # 兜底：含 证明/打印/下载 的可点击元素
    try:
        hit = page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('a,button'));
            const kw = ['证明','打印','下载','导出'];
            const t = els.find(e => (e.innerText||'').trim() && kw.some(k => (e.innerText||'').includes(k)));
            return t ? (e=>e.innerText)(t).trim().slice(0,30) : null;
        }""")
        if hit:
            loc = page.locator(f'a:has-text("{hit}"), button:has-text("{hit}")').first
            if loc.count():
                return loc
    except Exception:
        pass
    return None


def download_proof(page, ctx):
    """点击证明按钮并保存 PDF。返回保存路径或 None。"""
    btn = find_proof_button(page)
    if not btn:
        return None, "no_button"
    log(f"找到证明按钮，点击…")
    out_pdf = os.path.join(PROOF_DIR, f"会计专业技术人员继续教育学习证明_{TODAY}.pdf")
    os.makedirs(PROOF_DIR, exist_ok=True)
    saved = None
    # 方式 1：浏览器文件下载
    try:
        from playwright.sync_api import TimeoutError as PWTimeout
        with page.expect_download(timeout=30000) as dl_info:
            btn.click()
        dl = dl_info.value
        dl.save_as(out_pdf)
        saved = out_pdf
        log(f"下载完成（文件下载）: {out_pdf}")
    except Exception as e:
        log(f"文件下载方式未触发（{type(e).__name__}），尝试打印预览…")
    # 方式 2：新标签页 / 打印预览
    if not saved:
        try:
            time.sleep(4)
            target = page
            if len(ctx.pages) > 1:
                target = ctx.pages[-1]
            target.wait_for_timeout(3000)
            target.pdf(path=out_pdf, print_background=True,
                       format="A4", margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            saved = out_pdf
            log(f"保存完成（打印预览 PDF）: {out_pdf}")
        except Exception as e:
            log(f"打印预览方式也失败: {type(e).__name__} {e}")
    return saved, ("ok" if saved else "download_failed")


def main():
    if len(sys.argv) > 1:
        try:
            wait_minutes = int(sys.argv[1])
        except ValueError:
            wait_minutes = 180
    else:
        wait_minutes = 180

    if not os.path.exists(STATE_FILE):
        log("错误：未找到登录态 jxjy_state.json，请先运行 jxjy_login_window.py 登录")
        sys.exit(2)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=STATE_FILE, viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        deadline = time.time() + wait_minutes * 60
        try:
            # 进入学习中心
            try:
                open_learning_center(page)
            except RuntimeError as e:
                log(str(e))
                sys.exit(2)

            # 轮询：等达标
            while time.time() < deadline:
                total = read_total_credit(page)
                log(f"平台总学分: {total}")
                if total is not None and total >= 90 - 0.01:
                    log("已达标，定位证明按钮…")
                    saved, status = download_proof(page, ctx)
                    if saved:
                        # 复制为项目根指定文件名
                        root_copy = os.path.join(ROOT, "会计专业技术人员继续教育学习证明.pdf")
                        import shutil
                        shutil.copyfile(saved, root_copy)
                        log(f"已复制到: {root_copy}")
                        # 刷新看板数据
                        try:
                            d = json.load(open(os.path.join(BASE, "jxjy_dashboard_data.json"), encoding="utf-8"))
                            d["cert_pulled_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            json.dump(d, open(os.path.join(BASE, "jxjy_dashboard_data.json"), "w", encoding="utf-8"),
                                      ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                        sys.exit(0)
                    elif status == "no_button":
                        log("达标但学习中心未出现证明按钮，截图待人工辨识…")
                        try:
                            page.screenshot(path=os.path.join(BASE, f"jxjy_cert_nobtn_{datetime.datetime.now():%H%M%S}.png"),
                                            full_page=True)
                        except Exception:
                            pass
                        sys.exit(4)
                    else:
                        log("点击证明按钮后未能保存文件，重试一次…")
                        time.sleep(5)
                        continue
                # 未达标，等 60 秒后复查
                log(f"未达标（{total}），{wait_minutes} 分钟内每 60 秒复查…")
                time.sleep(60)
                try:
                    open_learning_center(page)
                except RuntimeError:
                    log("复查时登录态失效")
                    sys.exit(2)
            log(f"等待 {wait_minutes} 分钟仍未达标，退出")
            sys.exit(3)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
