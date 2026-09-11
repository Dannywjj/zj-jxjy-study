# -*- coding: utf-8 -*-
"""
基于 jxjy_dashboard_data.json 更新本地继续教育看板。

用法：
  python jxjy_dashboard_updater.py [data.json]

数据文件默认：同目录 jxjy_dashboard_data.json
"""
import os, sys, json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WB = os.path.join(BASE, ".workbuddy")
DATA_FILE = os.path.join(WB, "jxjy_dashboard_data.json")
DASH_MAIN = os.path.join(WB, "jxjy_dashboard.html")
ZONGHE = os.path.join(BASE, "综合看板.html")


def load_data(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_main_dashboard(data):
    with open(DASH_MAIN, "r", encoding="utf-8") as f:
        html = f.read()

    total = data["total"]
    major = data["major"]
    pub = data["public"]
    total_pct = round(total["got"] / total["need"] * 100, 1)
    major_pct = round(major["got"] / major["need"] * 100, 1)
    remain = round(total["need"] - total["got"], 2)
    today = data["today_got"]
    updated = data["updated_at"]

    # 顶部更新时间
    html = re_sub(r'最后更新 \d{4}-\d{2}-\d{2} \d{2}:\d{2}', f'最后更新 {updated[:16]}', html)

    # 今日学习时长
    html = html.replace(
        '<div class="label"><span class="ic" style="background:#0e9f6e"></span>今日学习时长</div>',
        '<div class="label"><span class="ic" style="background:#0e9f6e"></span>今日学习时长</div>'
    )
    html = re_sub(
        r'<div class="value">[^<]*</div>\n\s*<div class="sub">继续教育自动挂课[^<]*</div>',
        f'<div class="value">约 {data["today_minutes"]} 分钟</div>\n      <div class="sub">继续教育自动挂课 · 本会话</div>',
        html
    )

    # 总学分进度（顶部 KPI）
    html = re_sub(
        r'<div class="value">\d+\.?\d*<span style="font-size:15px;color:#8a94a6;font-weight:500"> / 90</span></div>\n\s*<div class="sub">完成率 [\d.]+%</div>',
        f'<div class="value">{total["got"]}<span style="font-size:15px;color:#8a94a6;font-weight:500"> / {int(total["need"])}</span></div>\n      <div class="sub">完成率 {total_pct}%</div>',
        html
    )

    # 卡片字段：学员、年度、待学习、今日已获取（学费行已移除）
    html = re_sub(
        r'<div class="row"><span class="k">学员</span><span class="v">[^<]*</span></div>\s*<div class="row"><span class="k">年度</span><span class="v mono">\d{4}</span></div>\s*<div class="row"><span class="k">待学习的学分</span><span class="v mono">[\d.]+</span></div>\s*<div class="row"><span class="k">今日已获取的学分</span><span class="v mono" style="color:#[0-9a-fA-F]{6}">\+?[\d.]+</span></div>',
        f'''<div class="row"><span class="k">学员</span><span class="v">{data["student"]}</span></div>
        <div class="row"><span class="k">年度</span><span class="v mono">{data["year"]}</span></div>
        <div class="row"><span class="k">待学习的学分</span><span class="v mono">{remain:.2f}</span></div>
        <div class="row"><span class="k">今日已获取的学分</span><span class="v mono" style="color:#0e9f6e">+{today:.2f}</span></div>''',
        html
    )

    # 卡片进度条
    html = re_sub(
        r'<div class="p-head"><span class="k">总学分</span><span class="v">\d+\.?\d* <small>/ 90</small></span></div>\n\s*<div class="bar"><i style="width:[\d.]+%"></i></div>',
        f'<div class="p-head"><span class="k">总学分</span><span class="v">{total["got"]} <small>/ {int(total["need"])}</small></span></div>\n        <div class="bar"><i style="width:{total_pct}%"></i></div>',
        html
    )
    html = re_sub(
        r'<div class="p-head"><span class="k">专业课</span><span class="v">\d+\.?\d* <small>/ 60</small></span></div>\n\s*<div class="bar"><i style="width:[\d.]+%"></i></div>',
        f'<div class="p-head"><span class="k">专业课</span><span class="v">{major["got"]} <small>/ {int(major["need"])}</small></span></div>\n        <div class="bar"><i style="width:{major_pct}%"></i></div>',
        html
    )

    # 当前课程
    html = re_sub(
        r'<div class="row"><span class="k">当前课程</span><span class="v">[^<]*</span></div>',
        f'<div class="row"><span class="k">当前课程</span><span class="v">{data["current_course"]}</span></div>',
        html
    )

    # 弹窗 KPI-mini
    html = re_sub(
        r'<div class="km"><div class="t">总学分</div><div class="n">\d+\.?\d*<span style="font-size:13px;color:#8a94a6"> / 90</span></div></div>\n\s*<div class="km"><div class="t">专业课</div><div class="n">\d+\.?\d*<span style="font-size:13px;color:#8a94a6"> / 60</span></div></div>\n\s*<div class="km"><div class="t">公需课</div><div class="n">\d+\.?\d*<span style="font-size:13px;color:#8a94a6"> / 18</span></div></div>',
        f'''<div class="km"><div class="t">总学分</div><div class="n">{total["got"]}<span style="font-size:13px;color:#8a94a6"> / {int(total["need"])}</span></div></div>
        <div class="km"><div class="t">专业课</div><div class="n">{major["got"]}<span style="font-size:13px;color:#8a94a6"> / {int(major["need"])}</span></div></div>
        <div class="km"><div class="t">公需课</div><div class="n">{pub["got"]:.0f}<span style="font-size:13px;color:#8a94a6"> / {int(pub["need"])}</span></div></div>''',
        html
    )

    # 弹窗当前在学课程表
    html = re_sub(
        r'<tr><th style="width:130px">课程</th><td>[^<]*</td></tr>\n\s*<tr><th>进度</th><td>[^<]*</td></tr>\n\s*<tr><th>今日学习</th><td>[^<]*</td></tr>',
        f'''<tr><th style="width:130px">课程</th><td>{data["current_course"]}</td></tr>
        <tr><th>进度</th><td>{data["current_section"]}</td></tr>
        <tr><th>今日学习</th><td>约 {data["today_minutes"]} 分钟（本会话）</td></tr>''',
        html
    )

    with open(DASH_MAIN, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已更新: {DASH_MAIN}（财税工作自动化看板已停用，不再同步到根目录）")


def update_zonghe_dashboard(data):
    with open(ZONGHE, "r", encoding="utf-8") as f:
        html = f.read()

    total = data["total"]
    remain = round(total["need"] - total["got"], 2)
    today = data["today_got"]

    # 副标题
    html = re_sub(
        r'<div style="font-weight:600;">继续教育自动刷课</div>\n\s*<div style="opacity:\.7;font-size:11px;margin-top:2px;">[^<]*</div>',
        f'<div style="font-weight:600;">继续教育自动刷课</div>\n      <div style="opacity:.7;font-size:11px;margin-top:2px;">{data["current_course"]} · {data["current_section"].split(" · ")[0]} · 今日 +{today:.2f} 学分</div>',
        html
    )

    # 进度条初始值
    cur, dur = parse_section(data["current_section"])
    html = re_sub(
        r'<div style="font-size:13px;font-weight:600;" id="study-progress-text">\d{2}:\d{2}/\d{2}:\d{2}</div>',
        f'<div style="font-size:13px;font-weight:600;" id="study-progress-text">{cur}/{dur}</div>',
        html
    )
    html = re_sub(
        r'// 刷课进度（基于当前真实日志：[^）]*）\nlet studyCur = [\d\*\+\s]+, studyDur = [\d\*\+\s]+;',
        f'// 刷课进度（基于当前真实日志：{data["current_section"].split(" · ")[0]} {cur}/{dur}）\nlet studyCur = {time_to_sec(cur)}, studyDur = {time_to_sec(dur)};',
        html
    )

    # 学分概览列（学费字段已移除）
    html = re_sub(
        r'<div style="text-align:right;min-width:110px;">\s*<div style="font-size:13px;font-weight:600;">\d+\.?\d* <span style="font-size:11px;font-weight:500;opacity:\.7">/ 90</span></div>\s*<div style="opacity:\.7;font-size:11px;margin-top:2px;">待学 [\d.]+</div>\s*</div>',
        f'''<div style="text-align:right;min-width:110px;">
      <div style="font-size:13px;font-weight:600;">{total["got"]} <span style="font-size:11px;font-weight:500;opacity:.7">/ {int(total["need"])}</span></div>
      <div style="opacity:.7;font-size:11px;margin-top:2px;">待学 {remain:.2f}</div>
    </div>''',
        html
    )

    # 底部 auto-card meta（小时数用 \d+ 兼容后续调整；实际为 840 分钟 = 14 小时）
    html = re_sub(
        r'<div class="auto-meta">每日 09:00 启动 · \d+ 小时 · 已获得 .*?</div>',
        f'<div class="auto-meta">每日 09:00 启动 · 14 小时 · 已获得 {total["got"]}/{int(total["need"])} · 待学 {remain:.2f}</div>',
        html
    )

    # 「三大工作模块」继续教育卡片的 module-desc（此前遗漏未同步，属残留旧值）
    html = re_sub(
        r'<div class="module-desc">每日 09:00 自动挂课 [^<]*</div>',
        f'<div class="module-desc">每日 09:00 自动挂课 14 小时 · 已获 {total["got"]}/{int(total["need"])} 学分 · 待学 {remain:.2f} · 今日 +{today:.2f}</div>',
        html
    )

    with open(ZONGHE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已更新: {ZONGHE}")


def re_sub(pattern, repl, text):
    import re
    # 兼容 Windows CRLF 与 Unix LF 换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    result, count = re.subn(pattern, repl, text)
    if count == 0:
        print(f"警告：正则未匹配: {pattern[:60]}...")
    return result


def parse_section(section_str):
    """解析 '第 2 讲 · 约 04:42 / 41:54' -> ('04:42', '41:54')"""
    import re
    m = re.search(r'(\d{2}:\d{2})\s*/\s*(\d{2}:\d{2})', section_str)
    if m:
        return m.group(1), m.group(2)
    return "00:00", "00:00"


def time_to_sec(t):
    m, s = map(int, t.split(":"))
    return m * 60 + s


def main():
    data_path = sys.argv[1] if len(sys.argv) > 1 else DATA_FILE
    data = load_data(data_path)
    update_main_dashboard(data)
    update_zonghe_dashboard(data)
    print("看板更新完成")


if __name__ == "__main__":
    main()
