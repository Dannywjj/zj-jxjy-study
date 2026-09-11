# -*- coding: utf-8 -*-
"""探测8：翻页枚举『公需知识』全部课程。"""
import os, sys, time, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "jxjy_state.json")
SCHOOL = "https://jxjy.chinaacc.com/learningCenter"

VIS = """() => {
  const out=[];
  document.querySelectorAll('table tr').forEach(tr=>{
    if(tr.getBoundingClientRect().height<=0) return;
    const c=[...tr.querySelectorAll('td,th')].map(td=>(td.innerText||'').replace(/\\s+/g,' ').trim());
    if(c.length>=4 && c[1] && c[1] !== '课程名称') out.push(c);
  });
  return out;
}"""

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(storage_state=STATE, viewport={"width": 1600, "height": 1400})
    pg = ctx.new_page()
    pg.set_default_timeout(60000)
    pg.goto(SCHOOL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)

    el = pg.locator(".pc_cwaretype", has_text="公需知识").first
    el.scroll_into_view_if_needed(); time.sleep(1); el.click(timeout=10000)
    time.sleep(8)
    print("切到 公需知识，page1:")
    allrows = {}
    seen = set()

    def collect():
        rows = pg.evaluate(VIS)
        for r in rows:
            key = (r[0], r[1])
            if key not in seen:
                seen.add(key)
                allrows[key] = r
        return rows

    rows = collect()
    print("  page1 rows:", len(rows))
    # 翻页
    for pgno in list(range(2, 16)):
        clicked = pg.evaluate("""(n) => {
          const cands=[...document.querySelectorAll('a,span,div,li,button')];
          for(const e of cands){
            const t=(e.innerText||'').trim();
            if(t===String(n) && e.getBoundingClientRect().height>0 && e.tagName!=='TD'){
              e.click(); return true;
            }
          }
          return false;
        }""", pgno)
        if not clicked:
            print(f"  第{pgno}页 无翻页按钮，停止"); break
        time.sleep(6)
        rows = collect()
        print(f"  page{pgno} rows={len(rows)} 累计={len(allrows)}")
        if len(rows) == 0:
            break

    print()
    print(f"=== 公需知识 课程总数: {len(allrows)} ===")
    cats = {}
    for k, r in allrows.items():
        cats[r[0]] = cats.get(r[0], 0) + 1
    print("分类:", json.dumps(cats, ensure_ascii=False))
    for k, r in allrows.items():
        print("  ", json.dumps(r[:4] + ([r[-1]] if len(r) >= 5 else []), ensure_ascii=False))
    ctx.close(); b.close()
