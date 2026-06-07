#!/usr/bin/env python3
"""
check_consistency.py — DGXX 研究档案一致性检查（防"改一半"）

用途：每次更新 markdown 档案 / 重建站点后跑一遍，揪出：
  1) 残留的"过时/已被更正"表述（如"0 签约 AI 客户 / 没客户 / AI 收入至今 $0"），
     但允许出现在『更正语境』里（行内含 更正/误称/先前/v1.2 等标记则放行）。
  2) 关键事实「必须出现」断言（如 Cerebras / SubQ 应出现在核心档案里）。
  3) markdown 与已生成 HTML 的同步：每个 *.md 是否都有对应 site/*.html。

退出码：0=全部通过；1=发现问题（CI 友好）。

用法：
  python3 check_consistency.py            # 检查当前目录的 *.md + site/*.html
  python3 check_consistency.py --html     # 同时扫描 site/*.html 里的过时表述
  python3 check_consistency.py --dir /path/to/research
"""
import argparse
import os
import re
import sys

# ── 1) 过时表述黑名单（这些是已被 v1.2 更正的旧结论，正文里不该再当"现状"出现）──
STALE_PATTERNS = [
    r"付钱的\s*AI\s*客户.{0,6}(目前是|还是个|是)\s*0",
    r"没客户",
    r"尚未签约[·\s]*待落地",
    r"还没签下第一个\s*AI\s*客户",
    r"一个都还没签下",
    r"AI\s*收入至今\s*\$?0",
    r"有电、有机柜、没客户(?!\s*的待|，推进|.{0,4}阶段)",  # 排除"从…没客户→"过渡描述
    r"0\s*个?签约\s*AI\s*客户",
    r"AI\s*租户尚未签约",
]

# ── 允许放行的"更正语境"标记：行内出现任一即视为合法引用旧表述 ──
CORRECTION_MARKERS = [
    "更正", "误称", "误判", "先前", "v1.2", "从“没客户", "从\"没客户",
    "推进到", "已签约", "升级为", "变成", "尚未签约的未来合同",
]

# ── 2) 关键事实"必须出现"断言：{档案文件: [必须包含的关键词,...]} ──
MUST_CONTAIN = {
    "01_synthesis.md": ["Cerebras", "SubQ"],
    "10_industry.md": ["Cerebras", "SubQ"],
    "15_operating.md": ["Cerebras", "SubQ"],
    "25_contracts_valuation.md": ["Cerebras", "SubQ", "ASC 842"],
    "REPORT.md": ["Cerebras", "SubQ"],
    "18_plain_explainer.md": ["Cerebras", "SubQ"],
    "26_latest_developments.md": ["Vera Rubin", "Cerebras"],
}


def strip_html_tags(text):
    return re.sub(r"<[^>]+>", " ", text)


def scan_stale(path, scan_html=False):
    """返回 [(lineno, line, pattern), ...] 命中的过时表述（已排除更正语境）。"""
    hits = []
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return hits
    for i, raw in enumerate(lines, 1):
        line = strip_html_tags(raw) if path.endswith((".html", ".htm")) else raw
        if any(m in line for m in CORRECTION_MARKERS):
            continue  # 更正语境，放行
        for pat in STALE_PATTERNS:
            if re.search(pat, line):
                hits.append((i, line.strip()[:120], pat))
                break
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--html", action="store_true", help="同时扫描 site/*.html")
    args = ap.parse_args()
    d = args.dir
    problems = 0

    mds = sorted(f for f in os.listdir(d) if f.endswith(".md"))

    # 1) 过时表述
    print("【1】过时表述扫描（*.md）")
    for f in mds:
        hits = scan_stale(os.path.join(d, f))
        for ln, txt, pat in hits:
            print(f"  ❌ {f}:{ln}  «{txt}»  (pattern: {pat})")
            problems += 1
    site = os.path.join(d, "site")
    if args.html and os.path.isdir(site):
        for f in sorted(os.listdir(site)):
            if f.endswith(".html"):
                for ln, txt, pat in scan_stale(os.path.join(site, f), scan_html=True):
                    print(f"  ❌ site/{f}:{ln}  «{txt}»")
                    problems += 1
    if problems == 0:
        print("  ✅ 无残留过时表述")

    # 2) 必须出现的关键事实
    print("【2】关键事实必含断言")
    miss = 0
    for f, keys in MUST_CONTAIN.items():
        p = os.path.join(d, f)
        if not os.path.exists(p):
            print(f"  ⚠️ 缺文件 {f}")
            miss += 1
            continue
        txt = open(p, encoding="utf-8").read()
        for k in keys:
            if k not in txt:
                print(f"  ❌ {f} 缺关键词「{k}」")
                miss += 1
    if miss == 0:
        print("  ✅ 关键事实齐全")
    problems += miss

    # 3) md ↔ html 同步
    print("【3】markdown ↔ site/*.html 同步")
    sync = 0
    if os.path.isdir(site):
        html = set(x[:-5] for x in os.listdir(site) if x.endswith(".html"))
        skip = {"_INDEX", "check_consistency"}
        special = {"REPORT": "report", "18_plain_explainer": "explainer"}
        for f in mds:
            base = f[:-3]
            if base in skip:
                continue
            expect = special.get(base, base)
            if expect not in html:
                print(f"  ⚠️ {f} 无对应 site/{expect}.html（需重建？）")
                sync += 1
    if sync == 0:
        print("  ✅ 全部 md 均有对应 html")
    problems += sync

    print("─" * 40)
    if problems:
        print(f"❌ 发现 {problems} 处问题 → 退出码 1")
        return 1
    print("✅ 一致性检查全部通过 → 退出码 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
