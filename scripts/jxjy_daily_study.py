# -*- coding: utf-8 -*-
"""
浙江会计继续教育每日自动刷课脚本。

功能：
1. 从 jxjy_state.json 恢复登录态
2. 进入正保会计网校学习中心
3. 自动找到当前未完成的课程并播放
4. 持续挂视频，定时检查播放状态、关闭弹窗、处理暂停
5. 视频结束后自动进入下一课程/下一讲
6. 输出学习进度报告

用法：
  python jxjy_daily_study.py [分钟数]   # 默认运行 60 分钟
"""
import os, sys, json, time, datetime, traceback, re, subprocess, atexit
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "jxjy_state.json")
REPORT_FILE = os.path.join(BASE, "jxjy_study_report.json")
LOG_FILE = os.path.join(BASE, "jxjy_study.log")
DASH_DATA_FILE = os.path.join(BASE, "jxjy_dashboard_data.json")
UPDATER_FILE = os.path.join(BASE, "jxjy_dashboard_updater.py")
# 公需课学习计划（有序课程名单）。专业课达标后按此名单刷公需课。
PLAN_FILE = os.path.join(BASE, "jxjy_pubcourse_plan.json")

# 单实例锁：防止同一账号被两个会话同时登录而互踢
# （典型场景：跨天长会话仍在跑时，每日 09:00 自动任务又起一个新会话）
LOCK_FILE = os.path.join(BASE, "jxjy_study.lock")

DEFAULT_MINUTES = 480

# 最近一次抓到的学分总览（专业课未达标前用于判断是否切公需课）
LATEST_OVERVIEW = None

# 刷完自动关机功能已停用（默认不会关闭计算机）。
# 如需临时关机，请在操作系统层面单独执行 shutdown 命令。

# 浙江会计继续教育年度学分要求
CREDIT_REQUIREMENT = {"total": 90.0, "major": 60.0, "public": 18.0}

# 学习年度：默认取当前自然年。
# 跨年补学场景（例如 2027 年仍在补 2026 年度学分）用环境变量覆盖：set JXJY_YEAR=2026
STUDY_YEAR = int(os.environ.get("JXJY_YEAR") or datetime.datetime.now().year)


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_report(data):
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_credit_overview(page):
    """从学习中心页面抓取当年度学分总览。

    优先用「学分进度」文本精确解析（唯一、无歧义）：
      学习总学分进度： 51.6/90  专业课学分进度： 51.6/60  公需课学分进度： 0/18
    失败时回落到旧版表格行扫描。
    """
    # 方案 A：学分进度文本
    try:
        body = page.evaluate("() => document.body.innerText").replace("\n", " ")
        mt = re.search(r"总学分进度[：:]\s*([\d.]+)\s*/\s*([\d.]+)", body)
        mm = re.search(r"专业课学分进度[：:]\s*([\d.]+)\s*/\s*([\d.]+)", body)
        mp = re.search(r"公需课学分进度[：:]\s*([\d.]+)\s*/\s*([\d.]+)", body)
        if mt and mm and mp:
            return {
                "year": STUDY_YEAR,
                "total_got": float(mt.group(1)),
                "major_got": float(mm.group(1)),
                "public_got": float(mp.group(1)),
            }
    except Exception:
        pass
    # 方案 B（兜底）：表格行扫描（原逻辑）
    try:
        page.wait_for_selector("table tr", timeout=15000)
        rows = page.locator("table tr").all()
        for row in rows:
            try:
                text = row.inner_text().replace("\n", " ").replace("\t", " ")
            except Exception:
                continue
            if str(STUDY_YEAR) not in text:
                continue
            # 提取数字：年度 总学分 公需学分 专业学分
            nums = re.findall(r"\d+\.?\d*", text)
            if len(nums) >= 4:
                return {
                    "year": STUDY_YEAR,
                    "total_got": float(nums[1]),
                    "public_got": float(nums[2]),
                    "major_got": float(nums[3]),
                }
    except Exception as e:
        log(f"抓取学分总览失败: {e}")
    return None


def load_pubcourse_plan():
    """读取公需课学习计划的有序课程名单。返回 list[str]。"""
    if not os.path.exists(PLAN_FILE):
        return []
    try:
        with open(PLAN_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        names = []
        for c in d.get("courses", []):
            if isinstance(c, dict) and c.get("name"):
                names.append(c["name"])
            elif isinstance(c, str) and c:
                names.append(c)
        return names
    except Exception as e:
        log(f"读取公需课计划失败: {e}")
        return []


def current_credit_state(study_page=None):
    """返回 (专业课已得, 公需课已得)。优先实时抓取，失败回落到缓存 / 看板 JSON。"""
    global LATEST_OVERVIEW
    if study_page is not None:
        try:
            ov = fetch_credit_overview(study_page)
            if ov:
                LATEST_OVERVIEW = ov
                try:
                    save_dashboard_data(ov)
                except Exception:
                    pass
                return ov["major_got"], ov["public_got"]
        except Exception as e:
            log(f"实时抓学分失败，改用缓存: {e}")
    if LATEST_OVERVIEW:
        return LATEST_OVERVIEW["major_got"], LATEST_OVERVIEW["public_got"]
    try:
        with open(DASH_DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("major", {}).get("got", 0.0), d.get("public", {}).get("got", 0.0)
    except Exception:
        return 0.0, 0.0


def should_do_public(study_page=None):
    """判断本次是否该刷公需课：专业课已达标(>=60) 且 公需课未达标(<18)。

    刚跑完一门课时学分入账可能滞后，用 wait_fresh 参数让调用方传「刚结束的旧专业课学分」，
    这里会等待学分刷新，避免把刚刷完的专业课又当成未达标而重复选专业课。
    """
    major_need = CREDIT_REQUIREMENT["major"]
    pub_need = CREDIT_REQUIREMENT["public"]
    major_got, public_got = current_credit_state(study_page)
    if public_got >= pub_need - 0.01:
        log(f"学分判定: 专业{major_got}/{major_need} 公需{public_got}/{pub_need} -> 公需课已达标，常规模式")
        return False
    decided = major_got >= major_need - 0.01
    log(f"学分判定: 专业{major_got}/{major_need} 公需{public_got}/{pub_need} -> {'公需课模式' if decided else '常规专业课模式'}")
    return decided


def credits_done():
    """年度学分是否已全部达标（总 ≥90）。

    用于「刷完即关机」的完成态判定：达标后报告 status 置为 all_courses_done，
    自动关机看门狗（jxjy_auto_shutdown.py --on-all-done）据此立即关机。
    注意：原先脚本只输出 time_up / done_no_more_courses，
    看门狗认的 all_courses_done 永远不会出现 →「刷完再关机」形同虚设。
    """
    total_got = None
    if LATEST_OVERVIEW:
        total_got = LATEST_OVERVIEW.get("total_got")
    if total_got is None:
        d = load_dashboard_data()
        total_got = d.get("total", {}).get("got", 0.0)
    try:
        total_got = float(total_got or 0.0)
    except (TypeError, ValueError):
        total_got = 0.0
    need = CREDIT_REQUIREMENT["total"]
    return total_got >= need - 0.01, f"总学分 {total_got}/{need}"


def search_course_row(study_page, name, tries=3):
    """在学习中心用课程搜索框按名称精确定位课程行。返回 row locator 或 None。

    实测：输入框为 #courseSearch0，需点 a.searchBth 触发（合成事件无效）。
    """
    box = study_page.locator("#courseSearch0").first
    for attempt in range(tries):
        try:
            box.scroll_into_view_if_needed(timeout=5000)
            box.click(timeout=5000)
            box.fill("")
            box.type(name, delay=25)
        except Exception as e:
            log(f"输入搜索词失败({name}): {e}")
            study_page.wait_for_timeout(2000)
            continue
        clicked = False
        for sel in ("a.searchBth", ".searchBth", "i.searchBth", "a.fr.searchBth"):
            try:
                study_page.locator(sel).first.click(timeout=4000)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            try:
                box.press("Enter")
            except Exception:
                pass
        study_page.wait_for_timeout(4000)
        try:
            rows = study_page.locator("table tr")
            for i in range(rows.count()):
                row = rows.nth(i)
                try:
                    text = row.inner_text().replace("\n", " ")
                except Exception:
                    continue
                if text and name in text:
                    return row
        except Exception as e:
            log(f"搜索后读取表格失败: {e}")
        log(f"第 {attempt + 1} 次未搜到课程[{name}]，重试…")
    return None


def load_dashboard_data():
    """加载现有看板数据。"""
    if not os.path.exists(DASH_DATA_FILE):
        return {}
    try:
        with open(DASH_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_dashboard_data(overview, current_course=None, current_section=None, today_minutes=0):
    """保存/更新继续教育看板数据文件。"""
    try:
        old = load_dashboard_data()
        total_need = CREDIT_REQUIREMENT["total"]
        major_need = CREDIT_REQUIREMENT["major"]
        pub_need = CREDIT_REQUIREMENT["public"]
        total_got = overview.get("total_got", 0.0) if overview else old.get("total", {}).get("got", 0.0)
        major_got = overview.get("major_got", 0.0) if overview else old.get("major", {}).get("got", 0.0)
        pub_got = overview.get("public_got", 0.0) if overview else old.get("public", {}).get("got", 0.0)

        # 今日已获取学分：以「当天起点学分」day_base 为基线。
        # 原逻辑用「上次文件里的总分」当基线，导致同一轮里第二次保存就算出 0
        # （因为刷课过程中会多次以 overview=None 调用本函数，total_got 取自旧文件）。
        today_key = datetime.date.today().isoformat()
        if old.get("day_key") == today_key and isinstance(old.get("day_base"), (int, float)):
            day_base = old["day_base"]
        else:
            # 跨天（或旧文件缺基线）：以上一次记录的总学分作为今日起点
            day_base = old.get("total", {}).get("got", total_got)
        today_got = round(total_got - day_base, 2)
        if today_got < 0:
            # 基线异常（取到了更大的旧值）→ 归零并以当前值为新基线
            day_base = total_got
            today_got = 0.0

        data = {
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "year": STUDY_YEAR,
            "student": old.get("student", "学员"),
            "total": {"got": total_got, "need": total_need},
            "major": {"got": major_got, "need": major_need},
            "public": {"got": pub_got, "need": pub_need},
            "today_got": today_got,
            "today_got_note": f"较今日起点（{day_base:.2f}）增加",
            "day_key": today_key,
            "day_base": day_base,
            "today_minutes": today_minutes or old.get("today_minutes", 0),
            "current_course": current_course or old.get("current_course", ""),
            "current_section": current_section or old.get("current_section", ""),
            "schedule": old.get("schedule", "每日 09:00 · 14 小时"),
            "source": old.get("source", "学习中心页面 + 刷课日志"),
        }
        with open(DASH_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"看板数据已保存: {DASH_DATA_FILE}")
    except Exception as e:
        log(f"保存看板数据失败: {e}")


def update_dashboard_html():
    """调用 updater 脚本刷新本地 HTML 看板。"""
    try:
        if not os.path.exists(UPDATER_FILE):
            return
        subprocess.run(
            [sys.executable, UPDATER_FILE, DASH_DATA_FILE],
            cwd=BASE,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        log("本地 HTML 看板已刷新")
    except Exception as e:
        log(f"刷新 HTML 看板失败: {e}")


def close_annoying(page):
    """关闭弹窗、点击继续学习等可能中断播放的元素。"""
    try:
        # 常见中断按钮：继续学习、继续播放、确定、知道了、下一讲、下一节
        texts = ["继续学习", "继续播放", "确定", "知道了", "继续", "下一讲", "下一节", "关闭", "下次再说"]
        for txt in texts:
            try:
                btns = page.locator(f"button:has-text('{txt}'):visible, a:has-text('{txt}'):visible").all()
                for btn in btns:
                    try:
                        if btn.is_visible():
                            btn.click(timeout=2000)
                            log(f"[click] {txt}")
                            time.sleep(0.5)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception as e:
        log(f"[close_annoying err] {e}")


def video_status(page):
    """读取 video 元素状态。NaN 一律归零，防止下游格式化崩溃。"""
    try:
        st = page.evaluate("""() => {
            const v = document.querySelector('video');
            if (!v) return null;
            return {
                currentTime: v.currentTime,
                duration: v.duration,
                paused: v.paused,
                ended: v.ended,
                muted: v.muted,
                volume: v.volume,
                readyState: v.readyState,
                playbackRate: v.playbackRate,
                src: v.src ? v.src.slice(0, 80) : ''
            };
        }""")
        if st:  # JS 返回的 NaN 经 JSON 序列化会变 None 或非法值，统一兜底
            for k in ("currentTime", "duration"):
                v = st.get(k)
                if v is None or v != v:
                    st[k] = 0
        return st
    except Exception as e:
        return {"error": str(e)}


def ensure_playing(page):
    """确保视频在播放。"""
    try:
        page.evaluate("""() => {
            const v = document.querySelector('video');
            if (v) {
                v.muted = true;
                if (v.paused) { v.play(); }
                v.playbackRate = 1.0;
            }
        }""")
    except Exception as e:
        log(f"[ensure_playing err] {e}")


def persist_state(ctx, path=STATE_FILE):
    """把当前 context 的 storage_state 写回文件，持久化正保等动态 cookie。"""
    try:
        state = ctx.storage_state()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        log(f"登录态已刷新保存: {path}")
    except Exception as e:
        log(f"保存登录态失败: {e}")


def click_next_section(play_page):
    """在当前课程页点击下一讲（第02讲/第03讲...），返回是否成功。"""
    try:
        links = play_page.locator('a.akuo:visible').all()
        if not links:
            return False
        current_idx = -1
        for i, link in enumerate(links):
            cls = (link.get_attribute('class') or '').lower()
            if 'active' in cls or 'current' in cls or 'on' in cls:
                current_idx = i
                break
        next_idx = current_idx + 1 if current_idx >= 0 else 1
        if next_idx >= len(links):
            return False
        nxt = links[next_idx]
        txt = nxt.inner_text().strip()
        nxt.click(timeout=5000)
        log(f"点击下一讲: {txt}")
        for _ in range(25):
            play_page.wait_for_timeout(2000)
            try:
                if play_page.evaluate("() => document.querySelectorAll('video').length") > 0:
                    log("下一讲视频已加载")
                    return True
            except Exception:
                pass
        return False
    except Exception as e:
        log(f"点击下一讲失败: {e}")
    return False


def open_learning_center(ctx):
    """进入浙江继续教育学习中心 → 点继续学习进选课页 → 点正保继续学习，返回正保学习中心页面。

    注意：选课页 goSelectSchoolNew.html 直接访问会被服务端重定向回首页，
    必须先经过学习中心 golearncenterNew.html 的"继续学习"按钮进入（带 referer）。
    """
    page = ctx.new_page()

    # 第一步：进入学习中心（学分总览页），带重试防止偶发重定向回首页
    # 第一阶段：直接访问，绕过"首页"中转；如被重定向到政务网登录页，则用方案 B
    for attempt in range(4):
        page.goto("https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        if "golearncenterNew" in page.url:
            break
        log(f"学习中心被重定向到 {page.url}，第 {attempt + 1} 次重试")
    # 兜底：如果最终仍被踢到政务网登录页，先访问首页建立会话，再跳转学习中心
    if "user.zjzwfw.gov.cn" in page.url:
        log("登录态过期，先访问首页建立会话")
        page.goto("https://jxjy.czt.zj.gov.cn/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        # 从首页跳学习中心（带 referer）
        page.goto("https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
    log(f"学习中心已打开: {page.url}")

    # 抓取当年度学分总览并保存（用于看板展示）
    try:
        overview = fetch_credit_overview(page)
        if overview:
            log(f"学分总览: 总{overview['total_got']} / 专业{overview['major_got']} / 公需{overview['public_got']}")
            save_dashboard_data(overview)
    except Exception as e:
        log(f"记录学分总览时出错: {e}")

    # 第二步：点击"继续学习"进入选课页（网校列表）
    # 兼容：如果不在学习中心，仍被踢到首页/政务网，截图后抛错以便排错
    if "golearncenterNew" not in page.url:
        shot = os.path.join(BASE, f"jxjy_fail_no_center_{datetime.datetime.now():%H%M%S}.png")
        try:
            page.screenshot(path=shot, full_page=True)
        except Exception:
            pass
        log(f"未能进入学习中心（停留在 {page.url}），截图 {shot}")
        raise RuntimeError(f"未能进入学习中心页面: {page.url}")
    btn1 = page.locator('a.btn-success:has-text("继续学习"):visible').first
    btn1.wait_for(state="visible", timeout=15000)
    btn1.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(5000)
    log(f"选课页已打开: {page.url}")

    # 第三步：点击"正保会计网校"所在行的"继续学习"按钮，进入正保学习中心。
    # 选课页有多个网校，每个网校一行都有"继续学习"，必须精确限定到正保这一行，
    # 否则可能点到其他未报名网校，导致 cookie 和课程列表错误。
    page.locator('text=正保会计网校').wait_for(state="visible", timeout=15000)
    zhengbao_row = page.locator('div.row:has-text("正保会计网校")').first
    # 兼容可能的 DOM 结构变化：div.row / div.panel / tr / 通用容器
    if not zhengbao_row.count():
        for sel in ('div.panel:has-text("正保会计网校")', 'tr:has-text("正保会计网校")',
                    'div:has(> :has-text("正保会计网校"))'):
            zhengbao_row = page.locator(sel).first
            if zhengbao_row.count():
                break
    if not zhengbao_row.count():
        raise RuntimeError("选课页未找到 正保会计网校 所在容器")
    btn2 = zhengbao_row.locator('a:has-text("继续学习"), button:has-text("继续学习")').first
    btn2.wait_for(state="visible", timeout=15000)
    with ctx.expect_page(timeout=60000) as info:
        btn2.click()
    study = info.value
    study.wait_for_load_state("domcontentloaded")
    study.wait_for_timeout(5000)
    log(f"正保学习中心已打开: {study.url}")
    # 此时正保 cookie 已建立，持久化登录态以便下次复用
    persist_state(ctx)
    return study


def is_course_row_completed(row_text):
    """根据课程行文本判断该课程学分是否已经拿满。

    判断依据（任一满足即认为已完成）：
    1. 已完成/要求学分：已完成 >= 要求学分（如 3.34/3.34 学分）
    2. 剩余学习时长为 0（如 0/150 分钟）
    3. 学习状态列包含"完成学习"或"已完成"
    """
    row_text = row_text.replace("\n", " ").replace("\t", " ")

    # 1. 学分已满
    m = re.search(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*学分', row_text)
    if m:
        try:
            got = float(m.group(1))
            need = float(m.group(2))
            if need > 0 and got >= need - 0.01:
                return True, f"学分已满 {got}/{need}"
        except (ValueError, TypeError):
            pass

    # 2. 剩余时长为 0（已完成整个课程）
    m2 = re.search(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*分钟', row_text)
    if m2:
        try:
            left = float(m2.group(1))
            if left <= 0.01:
                return True, "剩余时长为 0"
        except (ValueError, TypeError):
            pass

    # 3. 学习状态文字兜底
    if "完成学习" in row_text or "已完成" in row_text:
        return True, "状态显示已完成"

    return False, ""


def find_current_course(study_page, skip=None, prefer_public=False, plan=None):
    """在学习中心选择要播放的课程行。

    选择优先级：
    0. prefer_public=True（专业课已达标、公需课未达标）→ 按公需课计划名单逐门搜索定位；
       名单全部完成/找不到时，退化为「公需知识」分类下顺序选课。
    1. 「继续学习」按钮 + 未完成 → in-progress，最优先（避免重启后切到新课）
    2. 「开始学习」按钮 + 未完成 → 新课，回退选项
    3. 已完成 / 在 skip 列表里的行一律跳过

    课程表格数据由 AJAX 异步加载，domcontentloaded 后可能需要数秒才渲染，
    因此这里带重试等待，避免过早判定"没有课程"。
    skip: list[str]，包含任意关键字的行将被跳过（用于跳过打不开的课程）。
    """
    # ---- 公需课模式：按计划名单精确定位 ----
    if prefer_public:
        for name in (plan or []):
            try:
                row = search_course_row(study_page, name)
            except Exception as e:
                log(f"搜索公需课[{name}]异常: {e}")
                row = None
            if row is None:
                log(f"公需课计划[{name}] 未在学习中心搜到，跳过该门")
                continue
            try:
                text = row.inner_text().replace("\n", " ")
            except Exception:
                text = ""
            completed, reason = is_course_row_completed(text)
            if completed:
                log(f"公需课[{name}] 已完成({reason})，看下一门")
                continue
            if skip and any(s in text for s in skip):
                log(f"公需课[{name}] 在跳过名单内，看下一门")
                continue
            return row
        # 计划全部完成或都搜不到 → 退化：切到「公需知识」分类顺序选课
        log("公需课计划已全部完成/未搜到，退化为「公需知识」分类顺序学习")
        try:
            # 先清空搜索框，避免残留关键字干扰分类列表
            try:
                sb = study_page.locator("#courseSearch0").first
                sb.fill("")
                for sel in ("a.searchBth", ".searchBth"):
                    try:
                        study_page.locator(sel).first.click(timeout=3000)
                        break
                    except Exception:
                        continue
                study_page.wait_for_timeout(3000)
            except Exception:
                pass
            tab = study_page.locator(".pc_cwaretype", has_text="公需知识").first
            tab.scroll_into_view_if_needed(timeout=5000)
            tab.click(timeout=8000)
            study_page.wait_for_timeout(5000)
        except Exception as e:
            log(f"切换「公需知识」分类失败: {e}")

    def _pick(button_keyword, label):
        for _ in range(8):
            rows = study_page.locator("table tr")
            if rows.count() > 0:
                for i in range(rows.count()):
                    row = rows.nth(i)
                    try:
                        text = row.inner_text()
                    except Exception:
                        continue
                    if button_keyword not in text:
                        continue
                    if skip and any(s in text for s in skip):
                        continue
                    completed, reason = is_course_row_completed(text)
                    if completed:
                        log(f"跳过已完成课程 ({reason}) [{label}]: {text[:80].replace(chr(10), ' ')}")
                        continue
                    return row
            study_page.wait_for_timeout(3000)
        return None

    row = _pick("继续学习", "in-progress")
    if row is not None:
        return row
    return _pick("开始学习", "new")


def enter_course(study_page, ctx, skip=None, prefer_public=False, plan=None):
    """从学习中心点击课程行的继续学习/开始学习，返回 (播放页, 课程行文本)。

    兼容三种打开方式：新标签页 / 学习中心本页跳转 / 复用已有标签页。
    """
    row = find_current_course(study_page, skip=skip, prefer_public=prefer_public, plan=plan)
    if not row:
        return None, None
    text = row.inner_text().replace("\n", " ")
    log(f"选中课程: {text[:80]}")
    link = row.locator('a:has-text("继续学习"), a:has-text("开始学习")').first
    before_urls = set()
    try:
        before_urls = {pg.url for pg in ctx.pages}
    except Exception:
        pass
    before_study_url = study_page.url

    # 方式1：新开标签页（常规情况）
    try:
        with ctx.expect_page(timeout=30000) as info:
            try:
                # 提取链接 onclick 参数（如 isStudyThisCourse(courseId, classId, schoolId, type, ?)），
                # 直接在页面作用域内调用，最稳（不依赖元素可见性 / CSS）
                onclick_text = link.evaluate("el => el.getAttribute('onclick')")
                if onclick_text and onclick_text.strip():
                    fn_match = re.search(r"([A-Za-z_][\w]*)\s*\(([^)]*)\)", onclick_text)
                    if fn_match:
                        fn_name = fn_match.group(1)
                        fn_args = fn_match.group(2)
                        # 在页面作用域里直接调用
                        study_page.evaluate(f"() => {{ if (typeof {fn_name} === 'function') {{ {fn_name}({fn_args}); }} }}")
                        log(f"已通过 evaluate 触发: {fn_name}({fn_args[:60]})")
                    else:
                        # fallback：click force
                        link.click(timeout=10000, force=True)
                else:
                    link.click(timeout=10000, force=True)
            except Exception as ce:
                log(f"点击课程链接失败: {ce}")
                return None, text
        play = info.value
        play.wait_for_load_state("domcontentloaded", timeout=30000)
        play.wait_for_timeout(3000)
        log(f"进入课程页(新标签页): {play.url}")
        return play, text
    except Exception:
        log("30秒内未等到新标签页，尝试识别同页跳转/已有页复用…")

    # 方式2：学习中心本页跳转；方式3：复用已有标签页导航到课程页
    for _ in range(15):
        study_page.wait_for_timeout(2000)
        try:
            if study_page.url != before_study_url:
                study_page.wait_for_load_state("domcontentloaded", timeout=15000)
                log(f"进入课程页(本页跳转): {study_page.url}")
                return study_page, text
            for pg in ctx.pages:
                u = pg.url
                if (u and u not in before_urls and "courseware" in u
                        and "golearncenter" not in u and "goSelectSchool" not in u):
                    try:
                        pg.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    log(f"进入课程页(复用页面): {u}")
                    return pg, text
        except Exception:
            pass
    log(f"等待课程页打开超时，跳过该课程: {text[:60]}")
    return None, text


def wait_for_video(page, timeout_seconds=50):
    """在当前页面内等待 video 元素出现，或 URL 变为视频播放页。"""
    for _ in range(timeout_seconds // 2):
        try:
            if 'VideoPlayH5' in page.url:
                if page.evaluate("() => document.querySelectorAll('video').length") > 0:
                    return True
            elif page.evaluate("() => document.querySelectorAll('video').length") > 0:
                return True
        except Exception:
            pass
        page.wait_for_timeout(2000)
    return False


def start_video(play_page):
    """在课程页点击"继续学习/开始学习"大按钮，或点击章节目录，进入视频播放。"""
    try:
        # 1. 优先尝试"继续学习/开始学习"大按钮（已学课程常见）
        selectors = [
            'a.continue_studyNew',
            'a:has-text("开始学习")',
            'a:has-text("继续学习")',
            'button:has-text("开始学习")',
            'button:has-text("继续学习")',
        ]
        for sel in selectors:
            try:
                btn = play_page.locator(f'{sel}:visible').first
                if btn.count() > 0:
                    btn.click(timeout=5000)
                    log(f"点击学习大按钮 ({sel})")
                    if wait_for_video(play_page):
                        log("大按钮进入视频成功")
                        return play_page
                    break
            except Exception:
                continue

        # 2. 新版课程页（0/117分钟）是章节目录结构，没有大按钮，需点某一讲进入
        zhang = None
        for txt in ["第01讲", "第1讲", "第一讲"]:
            z = play_page.locator(f'a:has-text("{txt}"):visible').first
            if z.count() > 0:
                zhang = z; break
        if not zhang:
            z = play_page.locator('a.akuo:visible').first
            if z.count() > 0:
                zhang = z
        if zhang:
            zhang.click(timeout=5000)
            log("点击课程章节（第01讲）进入视频")
            if wait_for_video(play_page):
                log("章节进入视频成功")
                return play_page

        log("未找到学习入口或视频加载失败")
    except Exception as e:
        log(f"进入视频失败: {e}")
    return play_page


def _pid_alive(pid):
    """Windows 下判断进程是否存活"""
    try:
        # tasklist 在中文 Windows 输出 GBK；errors="replace" 避免解码异常，
        # PID 为纯数字 ASCII，不受影响
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10
        ).stdout
        return str(pid) in out
    except Exception:
        return False


def acquire_single_instance():
    """获取单实例锁。已有存活实例则返回 (False, 占用者PID)。"""
    try:
        if os.path.exists(LOCK_FILE):
            old = 0
            try:
                old = int(open(LOCK_FILE, encoding="utf-8").read().strip() or 0)
            except (ValueError, OSError):
                old = 0
            if old and old != os.getpid() and _pid_alive(old):
                return False, old
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True, os.getpid()
    except OSError as e:
        log(f"单实例锁异常（忽略，继续运行）: {e}")
        return True, os.getpid()


def release_single_instance():
    """仅当锁是本进程写的才删除，避免误删他人锁。"""
    try:
        if os.path.exists(LOCK_FILE):
            cur = open(LOCK_FILE, encoding="utf-8").read().strip()
            if cur == str(os.getpid()):
                os.remove(LOCK_FILE)
    except OSError:
        pass


def main():
    minutes = DEFAULT_MINUTES
    if len(sys.argv) > 1:
        try:
            minutes = int(sys.argv[1])
        except ValueError:
            pass
    log(f"=== 浙江会计继续教育每日刷课启动，目标运行 {minutes} 分钟 ===")

    # 单实例防护：已有存活实例在跑则直接退出，避免同账号互踢
    ok, holder = acquire_single_instance()
    if not ok:
        log(f"检测到已有刷课实例在运行（PID {holder}），本次跳过，避免同账号多会话互踢")
        sys.exit(0)
    atexit.register(release_single_instance)
    log(f"单实例锁已获取（PID {os.getpid()}）")

    if not os.path.exists(STATE_FILE):
        log("错误：未找到登录态文件 jxjy_state.json，请先运行 jxjy_login_window.py 登录")
        release_single_instance()
        sys.exit(1)

    end_time = time.time() + minutes * 60
    report = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_minutes": minutes,
        "courses": [],
        "status": "running"
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=STATE_FILE, viewport={"width":1600,"height":1000})

        try:
            study_page = open_learning_center(ctx)
            skipped_courses = []   # 打不开的课程，跳过避免死循环
            entry_fail = 0         # 连续进入课程失败计数
            course_finished = False  # 上一轮刚跑完一门课（用于等学分入账）

            while time.time() < end_time:
                # 学习中心本页被跳转走时（同页进入课程），重新打开学习中心
                try:
                    if "learningCenter" not in study_page.url:
                        study_page = open_learning_center(ctx)
                except Exception:
                    study_page = open_learning_center(ctx)

                # 刚跑完一门课时，学分入账可能滞后 —— 等它刷新，避免误判模式
                if course_finished:
                    course_finished = False
                    for _ in range(4):
                        major_got, public_got = current_credit_state(study_page)
                        if major_got >= CREDIT_REQUIREMENT["major"] - 0.01 or public_got >= CREDIT_REQUIREMENT["public"] - 0.01:
                            break
                        log(f"学分尚未入账(专业{major_got}/公需{public_got})，等 20 秒后复查…")
                        time.sleep(20)

                try:
                    prefer_public = should_do_public(study_page)
                except Exception as e:
                    log(f"模式判定异常，按常规专业课模式继续: {e}")
                    prefer_public = False

                # 学分一旦全部达标（总≥90）→ 标记完成并结束，交看门狗/自动化按"刷完即关机"处理
                try:
                    met, credit_desc = credits_done()
                    if met:
                        log(f"学分已全部达标（{credit_desc}），今日任务完成")
                        report["status"] = "all_courses_done"
                        break
                except Exception as e:
                    log(f"学分达标判定异常: {e}")

                plan = load_pubcourse_plan() if prefer_public else []

                try:
                    play_page, row_text = enter_course(study_page, ctx, skip=skipped_courses,
                                                       prefer_public=prefer_public, plan=plan)
                except Exception as e:
                    log(f"进入课程异常: {e}")
                    play_page, row_text = None, None

                if not play_page:
                    if row_text:
                        # 该课程打不开，记入跳过名单并重试下一个
                        # 用前 8 字符的科目关键作为 key（而非整行截断），保证下次 find_current_course
                        # 的 skip substring 匹配能稳定命中（row.inner_text() 含 tab 不会污染科目关键字）
                        key = row_text.strip().split()[0][:8] if row_text.strip().split() else row_text[:8]
                        skipped_courses.append(key)
                        entry_fail += 1
                        log(f"课程 [{key}] 无法进入，已加入跳过名单")
                        if entry_fail >= 8:
                            log("连续 8 门课程无法进入，结束今日任务")
                            report["status"] = "too_many_entry_failures"
                            break
                        continue
                    log("学习中心没有可继续学习的课程，今日任务完成")
                    report["status"] = "done_no_more_courses"
                    break
                entry_fail = 0

                play_page = start_video(play_page)
                course_url = play_page.url
                course_title = play_page.title()
                # 清理标题中的网校后缀
                course_title_clean = course_title.replace("-正保会计网校", "").replace("-中华会计网校", "").strip()
                log(f"开始播放: {course_title} | {course_url}")

                # 更新看板当前课程
                try:
                    save_dashboard_data(None, current_course=course_title_clean)
                except Exception:
                    pass

                course_entry = {
                    "title": course_title,
                    "url": course_url,
                    "start": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "end": None,
                    "watched_seconds": 0
                }
                last_t = time.time()
                last_ct = None
                stall_count = 0

                # 循环监控当前课程播放
                while time.time() < end_time:
                    close_annoying(play_page)
                    ensure_playing(play_page)
                    st = video_status(play_page)
                    now = time.time()
                    elapsed = now - last_t
                    last_t = now

                    if st and not st.get("error"):
                        current = st.get("currentTime", 0)
                        duration = st.get("duration", 0)
                        paused = st.get("paused", True)
                        ended = st.get("ended", False)
                        course_entry["watched_seconds"] += elapsed

                        # 每隔一段时间更新看板当前讲次进度
                        try:
                            section_num = "第 1 讲"
                            # 从 URL 或标题中推断讲次
                            url_lower = course_url.lower()
                            if "video" in url_lower:
                                m = re.search(r'video[^/]*/(\d+)', url_lower)
                                if m:
                                    section_num = f"第 {int(m.group(1))} 讲"
                            current_section = f"{section_num} · 约 {fmt(current)} / {fmt(duration)}"
                            save_dashboard_data(None, current_section=current_section, today_minutes=sum(c.get("watched_seconds", 0) for c in report["courses"]) // 60)
                        except Exception:
                            pass

                        log_msg = f"  {course_title[:20]} | current={fmt(current)}/{fmt(duration)} paused={paused} ended={ended}"
                        log(log_msg)

                        # 完成判定：正常 ended / 进度达末尾；以及「卡在末尾但不触发 ended」的兜底
                        # （个别课程媒体真实时长略小于播放器上报 duration，ended 不触发，current 卡在末尾不动）
                        near_end = duration > 0 and current >= duration * 0.95
                        if near_end and last_ct is not None and abs(current - last_ct) < 1.0:
                            stall_count += 1
                        else:
                            stall_count = 0
                        if ended or (duration > 0 and current >= duration - 8) or stall_count >= 3:
                            if stall_count >= 3:
                                log("视频卡在末尾(进度停滞)，按播完处理并推进下一讲/下一课")
                            else:
                                log("当前视频已播完")
                            course_entry["end"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            report["courses"].append(course_entry)
                            save_report(report)
                            # 先尝试同一课程下一讲
                            if click_next_section(play_page):
                                course_url = play_page.url
                                course_title = play_page.title()
                                log(f"开始播放下一讲: {course_title} | {course_url}")
                                course_entry = {
                                    "title": course_title,
                                    "url": course_url,
                                    "start": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "end": None,
                                    "watched_seconds": 0
                                }
                                last_t = time.time()
                                last_ct = None
                                stall_count = 0
                                continue
                            # 否则刷新学习中心，看是否有新课程
                            log("准备进入下一课程")
                            course_finished = True   # 标记刚跑完一门课，下轮先等学分入账
                            try:
                                if "learningCenter" in study_page.url:
                                    study_page.reload(wait_until="domcontentloaded", timeout=30000)
                                    study_page.wait_for_timeout(3000)
                                else:
                                    # 同页跳转场景：学习中心页已被课程页占用，重新打开
                                    study_page = open_learning_center(ctx)
                            except Exception as e:
                                log(f"刷新学习中心失败: {e}")
                                try:
                                    study_page = open_learning_center(ctx)
                                except Exception as e2:
                                    log(f"重新打开学习中心失败: {e2}")
                            break

                        last_ct = current
                    else:
                        log(f"  未检测到 video 元素或出错: {st}")

                    # 每 20 秒检查一次
                    time.sleep(20)
                else:
                    # 时间到了
                    course_entry["end"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    report["courses"].append(course_entry)
                    report["status"] = "time_up"
                    log("达到设定运行时长，退出")
                    break

        except Exception as e:
            log(f"运行异常: {e}\n{traceback.format_exc()}")
            report["status"] = "error"
            report["error"] = str(e)
        finally:
            save_report(report)
            # 结束时刷新看板数据与 HTML
            try:
                today_seconds = sum(c.get("watched_seconds", 0) for c in report.get("courses", []))
                save_dashboard_data(None, today_minutes=today_seconds // 60)
                update_dashboard_html()
            except Exception as e:
                log(f"结束时刷新看板失败: {e}")
            try:
                ctx.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
            log(f"=== 今日刷课结束，报告保存至 {REPORT_FILE} ===")
            # 刷完自动关机功能已停用——不再触发操作系统关机。
            # 保持浏览器/上下文清理与日志记录，照常退出。


def fmt(seconds):
    """秒数格式化为 mm:ss（NaN/None/负数一律返回 00:00，防止崩溃）"""
    try:
        if seconds is None or seconds != seconds or seconds < 0:  # seconds != seconds 即 NaN
            return "00:00"
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"
    except (TypeError, ValueError):
        return "00:00"


if __name__ == "__main__":
    main()
