# -*- coding: utf-8 -*-
"""
打包 zj-jxjy-study 并做发布前自检。

用法（在仓库根目录或任意位置均可）：
    python tools/build_package.py               # 私发版 dist/zj-jxjy-study_<ver>.zip
    python tools/build_package.py --marketplace # 市场上传版 dist/zj-jxjy-study_<ver>_marketplace.zip
    python tools/build_package.py --all         # 两个都打
    python tools/build_package.py --version 1.9.0   # 覆盖版本号（默认从 SKILL.md 读）

设计要点（都是踩过的坑，别改回去）：
  - REPO 由脚本自身位置推导，不写死绝对路径。历史上 dist 包里混进过使用者目录名。
  - VERSION 默认从 SKILL.md frontmatter 读取。历史上 dist zip 落后源码三个版本，
    就是因为版本号手填忘了改。
  - 自检覆盖四类：结构、脱敏、绝对路径泄漏、可移植性硬编码、版本一致性。
    其中「绝对路径泄漏」是 jxjy_chain_login_study_cert.sh 写死本机 python.exe
    换机器必炸之后加的门禁。
"""
import argparse
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = "scripts"
OUT_DIR = os.path.join(REPO, "dist")

# 真实私密串：这些一旦出现在包里，就是泄漏使用者身份/目录
LEAK_HARD = [
    "图图", "屠丹妮",
    "D:\\\\图图", "D:/图图",
    "C:\\\\Users\\\\admin", "C:/Users/admin",
]
# 绝对路径：换台机器必然跑不起来的元凶
USER_PATH = re.compile(
    r"[A-Za-z]:[\\/]+[Uu]sers[\\/]+[\w.\-]+"
    r"|/(?:c|C)/[Uu]sers/[\w.\-]+"
    r"|/home/[\w.\-]+/"
)
# 可移植性：换个账号 / 跨个年度就会失效的死值
PORT_BLOCK = [
    r'"year":\s*202[0-9]',
    r'syear=202[0-9]',
    r'^STUDY_ID\s*=\s*["\']\d+["\']',
]


def read_version(explicit=None):
    """从 SKILL.md frontmatter 读版本号。"""
    if explicit:
        return explicit
    p = os.path.join(REPO, "SKILL.md")
    if not os.path.isfile(p):
        sys.exit("[FATAL] 找不到 SKILL.md，无法推断版本")
    txt = open(p, encoding="utf-8").read()
    m = re.search(r"^version:\s*([0-9][0-9.]*)\s*$", txt, re.M)
    if not m:
        sys.exit("[FATAL] SKILL.md frontmatter 缺 version 字段")
    return m.group(1).rstrip(".")


def collect(kind):
    """按包类型收集待打包的相对路径。"""
    files = []
    if kind == "marketplace":
        # 市场包：解压即得 skill 目录，扁平，不带开发产物
        top = ["SKILL.md", "README.md", "LICENSE"]
    else:
        top = [".gitignore", "LICENSE", "README.md", "SKILL.md"]
    for n in top:
        if os.path.isfile(os.path.join(REPO, n)):
            files.append(n)
        else:
            print(f"  [WARN] 缺失顶层文件: {n}")
    sd = os.path.join(REPO, SCRIPTS)
    if not os.path.isdir(sd):
        sys.exit(f"[FATAL] 找不到 {SCRIPTS}/ 目录")
    for n in sorted(os.listdir(sd)):
        if n.endswith((".py", ".sh")):
            files.append(f"{SCRIPTS}/{n}")
    return files


def build(kind, version):
    files = collect(kind)
    suffix = "_marketplace" if kind == "marketplace" else ""
    out = os.path.join(OUT_DIR, f"zj-jxjy-study_{version}{suffix}.zip")
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            z.write(os.path.join(REPO, rel), rel)
    print(f"\n== 打包 {'市场上传版' if suffix else '私发版'} {version} ==")
    for f in files:
        print("   +", f)
    print(f"已生成: {out}  ({os.path.getsize(out)} bytes)")
    return out


def verify(out, kind, version):
    bad = 0
    sd = os.path.join(REPO, SCRIPTS)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()

        print("\n== 结构检查 ==")
        forbidden = [".git/", ".workbuddy/", "dist/", "_backup", "tools/"]
        if kind == "marketplace":
            forbidden.append(".gitignore")
        for f in forbidden:
            hit = [n for n in names if n.startswith(f)]
            if hit:
                print(f"  [FAIL] 混入 {f}: {hit}")
                bad += 1
        need = ["SKILL.md", "scripts/jxjy_setup.py",
                "scripts/jxjy_full_run.py", "scripts/jxjy_conf.py"]
        miss = [n for n in need if n not in names]
        if miss:
            print(f"  [FAIL] 缺少关键文件: {miss}")
            bad += 1
        n_py = len([n for n in names if n.startswith("scripts/") and n.endswith(".py")])
        print(f"  条目 {len(names)} 个，scripts/ 下 {n_py} 个 .py，"
              f"结构: {'通过' if bad == 0 else '有问题'}")

        print("\n== 脱敏 + 绝对路径泄漏 + 可移植性 ==")
        for n in names:
            try:
                txt = z.read(n).decode("utf-8")
            except UnicodeDecodeError:
                continue
            for kw in LEAK_HARD:
                if kw in txt:
                    print(f"  [FAIL] {n} 命中私密串 '{kw}'")
                    bad += 1
            for m in USER_PATH.finditer(txt):
                line = txt[:m.start()].count("\n") + 1
                print(f"  [FAIL] {n}:{line} 绝对路径 -> {m.group(0)}")
                bad += 1
            # 移植性只查代码：README 里出现年度是跨年示例说明，不是硬编码
            if n.startswith("scripts/"):
                for pat in PORT_BLOCK:
                    if re.search(pat, txt, re.M):
                        print(f"  [FAIL] {n} 仍硬编码 /{pat}/")
                        bad += 1
        print(f"  三项检查: {'通过' if bad == 0 else f'{bad} 处问题'}")

        print("\n== 版本一致性 ==")
        sk = z.read("SKILL.md").decode("utf-8")
        m = re.search(r"^version:\s*([0-9][0-9.]*)\s*$", sk, re.M)
        got = m.group(1).rstrip(".") if m else "?"
        ok = got == version
        print(f"  SKILL.md version {got} / 包版本 {version}  {'OK' if ok else '[FAIL]'}")
        if not ok:
            bad += 1
        lic = re.search(r"^license:\s*(\S+)", sk, re.M)
        print(f"  license: {lic.group(1) if lic else '未声明 [WARN]'}")
        # 文档里提到的脚本必须真实存在，否则就是失效引用
        refs = set(re.findall(r"`((?:jxjy_|refresh_jxjy_)[a-z_]+\.(?:py|sh))`", sk))
        missing = sorted(r for r in refs if r not in os.listdir(sd))
        print(f"  SKILL.md 引用脚本缺失: {missing if missing else '无'}")
        if missing:
            bad += 1
        if kind != "marketplace":
            rd = next((n for n in names if n.endswith("README.md")), None)
            if rd and "disable: true" not in z.read(rd).decode("utf-8"):
                print("  [WARN] README 未说明如何禁用 skill")

    print("\n总判定:", "可发布" if bad == 0 else f"{bad} 处问题，先修")
    return bad


def main():
    ap = argparse.ArgumentParser(description="打包 zj-jxjy-study 并自检")
    ap.add_argument("--marketplace", action="store_true", help="生成市场上传包")
    ap.add_argument("--all", action="store_true", help="两种包都生成")
    ap.add_argument("--version", help="覆盖版本号（默认从 SKILL.md 读）")
    a = ap.parse_args()

    version = read_version(a.version)
    kinds = ["marketplace", "dist"] if a.all else \
        (["marketplace"] if a.marketplace else ["dist"])

    total = 0
    for k in kinds:
        out = build(k, version)
        total += verify(out, k, version)
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
