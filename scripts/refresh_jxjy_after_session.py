# -*- coding: utf-8 -*-
"""刷课任务结束后抓取学习中心学分面板，更新看板数据与综合看板学分概览。"""
import os, sys, json, time
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "jxjy_state.json")
DATA = os.path.join(BASE, "jxjy_dashboard_data.json")

LEARN_URL = "https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html"
SELECT_URL = "https://jxjy.czt.zj.gov.cn/front/goSelectSchoolNew.html?syear=2026"
SCHOOL = "https://jxjy.chinaacc.com/learningCenter"

def fetch():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=STATE)
        page = ctx.new_page()
        page.goto(LEARN_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)
        # 进入选课页（如果还在学习中心页）
        if "golearncenterNew" in page.url:
            try:
                page.goto(SELECT_URL, wait_until="domcontentloaded", timeout=20000)
                time.sleep(1)
            except Exception as e:
                print(f"goSelectSchoolNew 失败: {e}")
        # 跳到正保会计网校学习中心
        page.goto(SCHOOL, wait_until="networkidle", timeout=45000)
        time.sleep(5)
        # 如果页面还在 loading 中，再等
        for _ in range(5):
            txt = page.evaluate("() => document.body.innerText")
            if "已完成" in txt or "学分" in txt and txt.count("/") > 5:
                break
            time.sleep(2)
        # 截全屏图
        shot = os.path.join(BASE, "jxjy_after_session.png")
        page.screenshot(path=shot, full_page=True)
        print(f"已截图: {shot}")
        # 提取学分概览（页面文本）
        body_text = page.evaluate("() => document.body.innerText")
        ctx.close()
        browser.close()
        return body_text, shot

def parse(text):
    """提取学分数字。例如：已获得学分 9.52/90、专业课 9.52/60 等。"""
    import re
    summary = {"raw_excerpt": "", "shots": []}
    # 截取与学分相关的片段
    for kw in ["学分", "总学分", "已完成", "已完成学分", "已获得"]:
        idx = text.find(kw)
        if idx >= 0:
            excerpt = text[max(0, idx-40): idx+200].replace("\n", " ").strip()
            if excerpt not in summary["shots"]:
                summary["shots"].append(excerpt)
    # 找 "xx.xx / 90" 这类配对
    matches = re.findall(r'(\d+\.\d{1,2})\s*/\s*(\d+\.?\d*)', text)
    if matches:
        summary["scores"] = matches[:15]
    return summary

if __name__ == "__main__":
    text, shot = fetch()
    info = parse(text)
    print(json.dumps(info, ensure_ascii=False, indent=2))