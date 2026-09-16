# -*- coding: utf-8 -*-
"""抓取正保学习中心学分面板，写入 jxjy_dashboard_data.json（供看板刷新脚本消费）。

用法：
  python refresh_jxjy_after_session.py

说明：
- 只抓数据、不刷课，约 30~60 秒。
- 学分文本解析优先用「学分进度」精确正则，失败回落表格行扫描。
- **防冲突**：若 jxjy_dashboard_data.json 在 60 秒内被修改过，说明刷课进程正在实时写同一文件，
  此时跳过写入（避免两个进程同时写坏 JSON），只打印结果。
- 保留文件里已有的 today_got / today_minutes / current_course 等字段——那些由刷课脚本负责维护。
"""
import os, sys, json, time, datetime, re
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "jxjy_state.json")
DATA = os.path.join(BASE, "jxjy_dashboard_data.json")

# 学习年度：默认取当前自然年；跨年补学场景可用 JXJY_YEAR 环境变量覆盖
STUDY_YEAR = int(os.environ.get("JXJY_YEAR") or datetime.datetime.now().year)

LEARN_URL = "https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html"
SELECT_URL = f"https://jxjy.czt.zj.gov.cn/front/goSelectSchoolNew.html?syear={STUDY_YEAR}"
SCHOOL = "https://jxjy.chinaacc.com/learningCenter"

CREDIT_REQUIREMENT = {"total": 90.0, "major": 60.0, "public": 18.0}


def fetch():
    """打开学习中心，返回 (body_text, 截图路径)。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=STATE)
        page = ctx.new_page()
        page.goto(LEARN_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)
        if "golearncenterNew" in page.url:
            try:
                page.goto(SELECT_URL, wait_until="domcontentloaded", timeout=20000)
                time.sleep(1)
            except Exception as e:
                print(f"goSelectSchoolNew 失败: {e}")
        page.goto(SCHOOL, wait_until="networkidle", timeout=45000)
        time.sleep(5)
        for _ in range(5):
            txt = page.evaluate("() => document.body.innerText")
            if "已完成" in txt or ("学分" in txt and txt.count("/") > 5):
                break
            time.sleep(2)
        shot = os.path.join(BASE, "jxjy_after_session.png")
        page.screenshot(path=shot, full_page=True)
        print(f"已截图: {shot}")
        body_text = page.evaluate("() => document.body.innerText")
        ctx.close()
        browser.close()
        return body_text, shot


def parse_credits(text):
    """从学习中心页面文本解析学分。返回 dict 或 None。

    优先精确匹配：
      学习总学分进度： 51.6/90  专业课学分进度： 51.6/60  公需课学分进度： 0/18
    """
    t = text.replace("\n", " ")

    def grab(pat):
        m = re.search(pat, t)
        return float(m.group(1)) if m else None

    total = grab(r"总学分进度[：:]\s*([\d.]+)")
    major = grab(r"专业课学分进度[：:]\s*([\d.]+)")
    pub = grab(r"公需课学分进度[：:]\s*([\d.]+)")
    if total is not None and major is not None and pub is not None:
        return {"total_got": total, "major_got": major, "public_got": pub, "via": "progress-text"}

    # 兜底：表格行「<年度> 总 公需 专业」
    for line in text.split("\n"):
        if str(STUDY_YEAR) not in line:
            continue
        nums = re.findall(r"\d+\.?\d*", line)
        if len(nums) >= 4:
            return {"total_got": float(nums[1]), "public_got": float(nums[2]),
                    "major_got": float(nums[3]), "via": "table-row"}
    return None


def save_credits(c):
    """把学分写回 jxjy_dashboard_data.json，保留其余字段。"""
    # 防冲突：文件 60 秒内被改过 = 刷课进程正在实时写
    if os.path.exists(DATA) and (time.time() - os.path.getmtime(DATA)) < 60:
        print("检测到刷课进程正在实时写数据（文件 60 秒内更新过），跳过写入以免冲突")
        return None
    try:
        with open(DATA, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data.setdefault("year", STUDY_YEAR)
    data.setdefault("student", "学员")
    data.setdefault("today_got", 0.0)
    data.setdefault("today_got_note", "较上次记录增加")
    data.setdefault("today_minutes", 0)
    data.setdefault("current_course", "")
    data.setdefault("current_section", "")
    data.setdefault("schedule", "每日 09:00 · 14 小时")
    data["total"] = {"got": c["total_got"], "need": CREDIT_REQUIREMENT["total"]}
    data["major"] = {"got": c["major_got"], "need": CREDIT_REQUIREMENT["major"]}
    data["public"] = {"got": c["public_got"], "need": CREDIT_REQUIREMENT["public"]}
    data["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["source"] = "refresh_jxjy_after_session.py（学习中心学分面板）"
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("已写入:", DATA)
    return data


if __name__ == "__main__":
    text, shot = fetch()
    credits = parse_credits(text)
    if not credits:
        print("未能解析到学分（登录态可能已过期，或被重定向到登录页）")
        sys.exit(2)
    print(f"学分: 总 {credits['total_got']}/{int(CREDIT_REQUIREMENT['total'])}"
          f" · 专业 {credits['major_got']}/{int(CREDIT_REQUIREMENT['major'])}"
          f" · 公需 {credits['public_got']}/{int(CREDIT_REQUIREMENT['public'])}"
          f"  (解析方式: {credits['via']})")
    saved = save_credits(credits)
    print("结果: 已落盘" if saved else "结果: 仅打印（未落盘）")
