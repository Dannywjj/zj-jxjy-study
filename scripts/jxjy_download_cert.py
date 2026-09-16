#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jxjy_download_cert.py —— 正保会计网校「继续教育学习证明（合格证）」自动拉取

交付物口径（已与用户确认 2026-09-14）：
  要的是【正保/浙江平台自己出具的官方证】，不是本地自制 HTML/PDF。
  正保侧可打印证书入口 = 学习中心「证书打印 / 合格证」→
      https://jxjy.chinaacc.com/mgt/certPrint?studyID=<学习计划ID>
  studyID 会随账号和年度变化，本脚本自动按以下顺序取值（见 resolve_study_id）：
      命令行 --study-id  >  环境变量 JXJY_STUDY_ID  >  学习中心页面动态识别  >  内置默认值

前置：
  1. 已登录（.workbuddy/jxjy_state.json 存在且 SSO 会话有效，< 9 小时）。
  2. 平台学分已 ≥90（总学分达标）。未达标时本脚本会在学习中心轮询等待，
     直到达标且证书可打印为止。

行为：
  - 直连 chinaacc /mgt/certPrint?studyID=<解析出的学习计划ID>（认 jxjy_state.json 的 mgt 会话）。
  - 页面出现「下载」类链接 → 逐个点击触发浏览器下载（PDF/JPG/XML），保存至：
        继续教育证明/继续教育学习证明_YYYY-MM-DD.pdf（及 .jpg/.xml）
        并复制为 项目根/会计专业技术人员继续教育学习证明.pdf
  - 若页面返回「未找到打印信息」→ 退出码 4：该学习计划当前尚未生成可打印证书
    （多半是计划仍在“进行中”，合格证需平台侧完结/刷新后才可打印；或 studyID 已变更）。
  - 兼容全国平台 ausm.mof.gov.cn「会计人员继续教育登记 → 学习证明」为权威备份源，
    但其 SPA 子模块在无头环境点击不触发路由，需真人可见浏览器操作，故本脚本主走正保侧。

用法：
  python jxjy_download_cert.py [wait_minutes] [--study-id NNNN | --study-id=NNNN]
      wait_minutes  达标且可打印前最多等待分钟数，默认 180（配合登录窗口 <9h）
      --study-id    手动指定正保学习计划 ID（换账号 / 跨年度报「未找到打印信息」时用）

退出码：
  0  成功下载
  2  登录态失效（mgt 会话无效）
  3  等待超时仍未达标 / 仍未可打印
  4  达标但平台「未找到打印信息」（证书暂不可打印，需平台侧完结/刷新或 studyID 变更）
"""
import os
import sys
import time
import json
import datetime
import shutil
import io
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "jxjy_state.json")
ROOT = os.path.dirname(BASE)                       # 项目根目录（即 .workbuddy 的上一级）
PROOF_DIR = os.path.join(ROOT, "继续教育证明")
DATA_FILE = os.path.join(BASE, "jxjy_dashboard_data.json")
TODAY = datetime.datetime.now().strftime("%Y-%m-%d")

# 正保学习计划 ID（studyID）。
# 解析优先级：命令行 --study-id  >  环境变量 JXJY_STUDY_ID  >  从学习中心页面动态识别  >  兜底默认值。
# 换账号或跨年度后若报「未找到打印信息」，多半是 studyID 变了，按上面的优先级显式指定即可。
DEFAULT_STUDY_ID = "21037"
STUDY_ID = None

LEARN_CENTER_URL = "https://jxjy.chinaacc.com/learningCenter"

_STUDY_ID_PATTERNS = (
    r"isStudyThisCourse\(\s*\d+\s*,\s*(\d+)\s*,",
    r"isContinueLearning\(\s*[\d, ]*?(\d{4,})\s*,",
    r"[?&]studyID=(\d+)",
)


def certprint_url():
    """按当前 STUDY_ID 拼出证书打印页地址。"""
    return f"https://jxjy.chinaacc.com/mgt/certPrint?studyID={STUDY_ID or DEFAULT_STUDY_ID}"


def detect_study_id(page):
    """从学习中心页面源码识别学习计划 ID，识别不到返回 None。"""
    try:
        html = page.content()
    except Exception:
        return None
    for pat in _STUDY_ID_PATTERNS:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def resolve_study_id(explicit=None, page=None):
    """确定最终的 STUDY_ID。explicit 为命令行传入值，page 用于动态识别。"""
    global STUDY_ID
    sid = explicit or os.environ.get("JXJY_STUDY_ID")
    how = "命令行 --study-id" if explicit else ("环境变量 JXJY_STUDY_ID" if sid else None)
    if not sid and page is not None:
        sid = detect_study_id(page)
        how = "学习中心页面动态识别"
    if not sid:
        sid, how = DEFAULT_STUDY_ID, "内置默认值（可能不适用于你的账号）"
    STUDY_ID = sid
    log(f"使用学习计划 ID {sid}（来源：{how}）")
    return sid

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.info


def total_credit_now():
    """读 jxjy_dashboard_data.json 的总学分（本地汇总，来自学习中心刷新）。"""
    try:
        d = json.load(open(DATA_FILE, encoding="utf-8"))
        return float(d.get("total", {}).get("got", 0.0))
    except Exception:
        return 0.0


def login_valid(ctx):
    """用 mgt 会话探一下：能进 certPrint 且未跳登录即有效。"""
    try:
        pg = ctx.new_page()
        pg.goto(certprint_url(), timeout=30000)
        pg.wait_for_timeout(4000)
        txt = (pg.evaluate("document.body.innerText") or "")
        url = pg.url
        pg.close()
        if "登录" in txt or "login" in url.lower():
            return False
        return True
    except Exception:
        return False


def pull(ctx):
    """打开 certPrint 页，点击所有「下载」链接，保存文件。返回 (saved_paths, status)。"""
    os.makedirs(PROOF_DIR, exist_ok=True)
    pg = ctx.new_page()
    pg.goto(certprint_url(), timeout=30000)
    pg.wait_for_timeout(6000)
    body = (pg.evaluate("document.body.innerText") or "")
    if "未找到打印信息" in body:
        log("平台返回「未找到打印信息」：该学习计划当前不可打印证书（需平台侧完结/刷新）。")
        pg.close()
        return [], "no_print_info"
    # 找「下载」类链接
    links = pg.locator("a").all()
    got = []
    for it in links:
        try:
            t = (it.inner_text() or "").strip()
        except Exception:
            continue
        if "下载" not in t:
            continue
        try:
            with pg.expect_download(timeout=30000) as dl_info:
                it.click()
            dl = dl_info.value
            ext = os.path.splitext(dl.suggested_filename)[1] or ".bin"
            # 固定文件名前缀（按用户要求）
            if ext.lower() == ".pdf":
                target_name = f"继续教育学习证明_{TODAY}.pdf"
            else:
                target_name = f"继续教育学习证明_{TODAY}{ext}"
            target = os.path.join(PROOF_DIR, target_name)
            dl.save_as(target)
            got.append(target)
            log(f"已下载: {target_name}")
        except Exception as e:
            log(f"[{t}] 下载失败: {type(e).__name__} {e}")
    pg.close()
    status = "ok" if got else "no_download_link"
    return got, status


def main():
    wait_minutes = 180
    explicit_study_id = None
    # 参数解析：<等待分钟数> [--study-id NNNN | --study-id=NNNN]
    args, positional = sys.argv[1:], []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--study-id" and i + 1 < len(args):
            explicit_study_id = args[i + 1].strip()
            i += 2
            continue
        if a.startswith("--study-id="):
            explicit_study_id = a.split("=", 1)[1].strip()
            i += 1
            continue
        positional.append(a)
        i += 1
    if positional:
        try:
            wait_minutes = int(positional[0])
        except ValueError:
            wait_minutes = 180

    if not os.path.exists(STATE_FILE):
        log("错误：未找到登录态 jxjy_state.json，请先运行 jxjy_login_window.py 登录")
        sys.exit(2)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=STATE_FILE,
                                  viewport={"width": 1600, "height": 1200},
                                  accept_downloads=True)
        # 先认一次学习计划 ID：换账号 / 跨年度时 studyID 可能不同，
        # 优先用学习中心页面里的真实 ID，避免使用过期的内置默认值。
        _probe = ctx.new_page()
        try:
            _probe.goto(LEARN_CENTER_URL, timeout=30000)
            _probe.wait_for_timeout(3000)
        except Exception:
            pass
        resolve_study_id(explicit_study_id, _probe)
        _probe.close()
        try:
            deadline = time.time() + wait_minutes * 60
            while time.time() < deadline:
                total = total_credit_now()
                log(f"本地汇总总学分: {total}")
                if total < 90 - 0.01:
                    log(f"未达标（{total}），{wait_minutes} 分钟内每 60 秒复查…")
                    time.sleep(60)
                    continue
                # 达标 → 探登录态
                if not login_valid(ctx):
                    log("登录态失效（mgt 会话无效），退出。")
                    sys.exit(2)
                # 拉证
                got, status = pull(ctx)
                if status == "ok":
                    # 复制 PDF 到项目根（固定交付名）
                    pdfs = [g for g in got if g.lower().endswith(".pdf")]
                    if pdfs:
                        root_copy = os.path.join(ROOT, "会计专业技术人员继续教育学习证明.pdf")
                        shutil.copyfile(pdfs[0], root_copy)
                        log(f"已复制到根目录: {root_copy}")
                    # 刷新看板数据
                    try:
                        d = json.load(open(DATA_FILE, encoding="utf-8"))
                        d["cert_pulled_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        d["cert_source"] = "正保会计网校学习中心（平台官方继续教育学习证明/合格证）"
                        json.dump(d, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    log(f"证书拉取完成：{got}")
                    sys.exit(0)
                elif status == "no_print_info":
                    # 达标但平台暂不可打印：等待平台刷新（学习计划完结后可打印）
                    log("证书暂不可打印，60 秒后重试（学习计划完结/刷新后可打印）…")
                    time.sleep(60)
                    continue
                else:
                    log("达标但页面无「下载」链接，60 秒后重试…")
                    time.sleep(60)
                    continue
            log(f"等待 {wait_minutes} 分钟仍未拉到证书，退出。")
            sys.exit(3)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
