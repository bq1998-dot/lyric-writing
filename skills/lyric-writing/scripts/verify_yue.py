#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""粤语歌词校验 · 通用版（lyric-writing skill）

把过去每写一首歌就重造一遍的校验逻辑固化成一个脚本。传歌词文件即可。

用法
----
  python verify_yue.py 歌词.txt
  python verify_yue.py 歌词.txt --focus 秋 --focus 傘
  python verify_yue.py 歌词.txt --genre ballad --bpm 78
  python verify_yue.py 歌词.txt --compare 另一份.txt      # 交付文本回比
  python verify_yue.py --check-table                      # 只自检注音表

歌词文件格式
------------
  [Verse 1]
  關上窗　整間屋靜到會痛
  ...
全角空格「　」作顿分隔；[标签] 行自成一段。

检查项
------
  ① 逐行字数 / 段内极差（含"呼吸点"判定）
  ② 韵脚韵部 / 声调（入声 FAIL、升调 WARN、平调 OK）+ 段内主韵一致性
  ③ 上声连用（FAIL）/ 三连上声（WARN）
  ④ 韵脚复押（按行文本折叠重复段后统计）
  ⑤ 焦点字渗透（--focus，看某字是否只落在句中、从不占韵脚）
  ⑥ 粤语特征字
  ⑦ 段长上限（按曲风 + BPM 感知）
  ⑧ 人味三指标（对照六首 90 年代真人经典得出，硬判定）
  ⑨ 交付文本回比（--compare）

退出码：有 FAIL → 1，否则 0
"""
import argparse
import os
import re
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyut import JyutEngine, is_checked, FLAT_TONES, RISING_TONES, CHECKED_CHARS

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---- 段长上限（Ballad 为默认；来源 references/section-limits.md）----
GENRE_LIMITS = {
    "ballad":  {"verse": 6, "chorus": 6, "bridge": 4, "pre": 4, "outro": 4},
    "pop":     {"verse": 8, "chorus": 6, "bridge": 4, "pre": 4, "outro": 4},
    "rock":    {"verse": 8, "chorus": 6, "bridge": 4, "pre": 4, "outro": 4},
    "folk":    {"verse": 8, "chorus": 6, "bridge": 4, "pre": 4, "outro": 4},
    "country": {"verse": 8, "chorus": 6, "bridge": 4, "pre": 4, "outro": 4},
    "rnb":     {"verse": 8, "chorus": 6, "bridge": 4, "pre": 4, "outro": 4},
    "jazz":    {"verse": 8, "chorus": 6, "bridge": 8, "pre": 4, "outro": 4},
    "rap":     {"verse": 8, "chorus": 6, "bridge": 6, "pre": 4, "outro": 4},
    "metal":   {"verse": 8, "chorus": 6, "bridge": 4, "pre": 4, "outro": 4},
    "edm":     {"verse": 6, "chorus": 4, "bridge": 4, "pre": 4, "outro": 4},
    "ambient": {"verse": 4, "chorus": 4, "bridge": 2, "pre": 4, "outro": 4},
    "punk":    {"verse": 6, "chorus": 4, "bridge": 4, "pre": 2, "outro": 4},
}

ZH_KIND = {"主歌": "verse", "副歌": "chorus", "桥段": "bridge", "橋段": "bridge",
           "预副歌": "pre", "前奏": "intro", "间奏": "instrumental",
           "尾奏": "outro", "主歌一": "verse", "主歌二": "verse"}

TRIM = "，。、！？；：,.!?;:…～~·「」『』（）()【】“”'\" \t"


def section_kind(name):
    n = name.strip().lower()
    if n in ZH_KIND:
        return ZH_KIND[n]
    if "pre" in n:
        return "pre"
    if "verse" in n:
        return "verse"
    if "chorus" in n:
        return "chorus"
    if "bridge" in n:
        return "bridge"
    if "outro" in n:
        return "outro"
    if "intro" in n:
        return "intro"
    if any(k in n for k in ("instrumental", "solo", "break", "interlude", "drop")):
        return "instrumental"
    return "unknown"


def parse(path):
    """-> [(段名, [行...]), ...]"""
    secs, cur = [], None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            s = raw.strip()
            if not s:
                continue
            if s.startswith("[") and s.endswith("]"):
                cur = [s[1:-1].strip(), []]
                secs.append(cur)
            elif cur is None:
                cur = ["(未命名)", []]
                secs.append(cur)
                cur[1].append(s)
            else:
                cur[1].append(s)
    return [(a, b) for a, b in secs]


def clean(t):
    return re.sub(r"[　\s]", "", t)


def rhyme_of(eng, line):
    """行末字（去尾部标点）-> (字, 韵母, 声调) 或 None"""
    c = clean(line).rstrip(TRIM)
    if not c:
        return None
    ch = c[-1]
    r = eng.lookup(ch)
    if not r:
        return None
    return (ch, r[1], r[2])


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("lyric", nargs="?", help="歌词 txt 路径")
    ap.add_argument("--focus", action="append", default=[], help="焦点字，可多次")
    ap.add_argument("--genre", default="ballad", help="曲风族（默认 ballad）")
    ap.add_argument("--bpm", type=int, default=0, help="BPM（<80 时主歌上限收紧到 4）")
    ap.add_argument("--compare", default="", help="另一份文件，逐行回比")
    ap.add_argument("--overrides", default="", help="外部多音字覆盖表（.py，dict）")
    ap.add_argument("--check-table", action="store_true", help="只自检注音表")
    args = ap.parse_args()

    eng = JyutEngine()
    if args.check_table:
        bad = eng.audit_table()
        print("pycantonese 可用:", eng.use_lib)
        print("S2T 坏映射:", bad if bad else "无")
        print("OVERRIDES:", eng.overrides)
        return 0 if not bad else 1

    if not args.lyric:
        ap.print_help()
        return 2
    if not os.path.exists(args.lyric):
        print("找不到文件:", args.lyric)
        return 2

    secs = parse(args.lyric)
    if not secs:
        print("解析不到任何内容:", args.lyric)
        return 2

    limits = dict(GENRE_LIMITS.get(args.genre.lower(), GENRE_LIMITS["ballad"]))
    if args.bpm and args.bpm < 80:
        limits["verse"] = min(limits["verse"], 4)

    fails, warns = [], []
    allc = "".join(clean(l) for _, ls in secs for l in ls)

    print("=" * 68)
    print(f"文件: {args.lyric}")
    print(f"曲风: {args.genre}   BPM: {args.bpm or '-'}   段长上限: {limits}")
    print("=" * 68)

    # ---- ① 字数与段内极差 ----
    print("\n① 逐行字数 / 段内极差")
    for name, ls in secs:
        if not ls:
            print(f"  {name:14s} (无词)")
            continue
        ns = [len(clean(l)) for l in ls]
        spread = max(ns) - min(ns)
        pairs = [(i, ns[i] - ns[i + 1]) for i in range(len(ns) - 1)]
        breath = [p for p in pairs if p[1] >= 4]
        if spread <= 2:
            flag = "OK"
        elif breath:
            flag = f"呼吸点 @ 第{breath[0][0]+1}行→第{breath[0][0]+2}行（差{breath[0][1]}，需文档点名）"
            warns.append(f"{name} 段内极差 {spread} 靠呼吸点成立，必须在交付文档点名")
        else:
            flag = "偏大且无呼吸点"
            fails.append(f"{name} 段内极差 {spread}，且不存在「长→短」相邻对（差≥4）")
        print(f"  {name:14s} {ns}  极差={spread}  {flag}")

    # ---- ② 韵脚 ----
    print("\n② 韵脚（末字）韵部 / 声调")
    table = []
    for name, ls in secs:
        rows = []
        for i, l in enumerate(ls):
            rr = rhyme_of(eng, l)
            if not rr:
                continue
            ch, fin, tone = rr
            if tone is None:
                fails.append(f"{name} 「{ch}」无注音，无法判韵")
                continue
            if is_checked(fin):
                tag = "入声!"
                fails.append(f"{name} 第{i+1}行韵脚「{ch}」是入声（{fin}），短促不能拖长")
            elif tone in RISING_TONES:
                tag = "升调"
                warns.append(f"{name} 第{i+1}行韵脚「{ch}」是升调（{tone}）——可作韵脚，但别落在需要拖长的长音上")
            else:
                tag = "平OK"
            rows.append((ch, fin, tone, tag))
            print(f"  {name:14s} …{ch}  {fin:6s} 调{tone}  {tag}")
        table.append((name, rows))
        fins = [r[1] for r in rows]
        if fins:
            cnt = Counter(fins)
            main, n = cnt.most_common(1)[0]
            ratio = n / len(fins)
            extra = [f for f in cnt if f != main]
            mark = "OK" if ratio == 1 else ("混韵" if ratio < 0.6 else "含刻意换韵")
            print(f"    → 段内主韵 {main} ({n}/{len(fins)}={ratio:.0%})  其他: {extra or '无'}  {mark}")
            if ratio < 0.6:
                warns.append(f"{name} 段内主韵只占 {ratio:.0%}，韵部不统一（若非刻意换韵应重排）")

    # ---- ③ 上声连用 ----
    print("\n③ 上声连用（相邻 2/5） / 三连上声")
    n_adj = 0
    for name, ls in secs:
        for i, l in enumerate(ls):
            c = clean(l)
            to = [(ch, eng.tone_of(ch)) for ch in c]
            miss = [ch for ch, t in to if t is None]
            if miss:
                warns.append(f"{name} 第{i+1}行有未注音字 {miss}")
                continue
            for k in range(len(to) - 1):
                if to[k][1] in RISING_TONES and to[k + 1][1] in RISING_TONES:
                    n_adj += 1
                    fails.append(f"{name} 第{i+1}行 上声连用：「{to[k][0]}{to[k+1][0]}」({to[k][1]}+{to[k+1][1]})")
            for k in range(len(to) - 2):
                s3 = {to[k][1], to[k + 1][1], to[k + 2][1]}
                if len(s3) == 1 and to[k][1] in RISING_TONES:
                    warns.append(f"{name} 第{i+1}行 三连上声：「{to[k][0]}{to[k+1][0]}{to[k+2][0]}」")
    print(f"  上声连用 {n_adj} 处" + ("（全部已列入 FAIL）" if n_adj else "  OK"))

    # ---- ④ 复押（折叠重复段）----
    print("\n④ 韵脚复押（相同文本的行折叠成一遍后统计）")
    seen, folded = OrderedDict(), []
    for name, ls in secs:
        for l in ls:
            key = clean(l)
            if key in seen:
                continue
            seen[key] = True
            rr = rhyme_of(eng, l)
            if rr:
                folded.append((name, rr[0], rr[1], rr[2]))
    cnt = Counter(f[1] for f in folded)
    print(f"  折叠后 {len(folded)} 位，不同字 {len(cnt)} 个")
    print("  序列: " + " ".join(f"{c}{f}{t}" for _, c, f, t in folded))
    for ch, n in cnt.items():
        if n > 2:
            warns.append(f"韵脚字「{ch}」折叠后仍重复 {n} 次（>2）")
    for i in range(len(folded) - 1):
        if folded[i][1] == folded[i + 1][1]:
            fails.append(f"相邻两行同韵脚字「{folded[i][1]}」（{folded[i][0]} ↔ {folded[i+1][0]}）")

    # ---- ⑤ 焦点字 ----
    if args.focus:
        print("\n⑤ 焦点字渗透")
        for f in args.focus:
            hits = [l for _, ls in secs for l in ls if f in clean(l)]
            uniq = OrderedDict()
            for l in hits:
                uniq.setdefault(clean(l), [l, 0])
                uniq[clean(l)][1] += 1
            rhyme_n = sum(1 for l in hits if (rhyme_of(eng, l) or (None,))[0] == f)
            print(f"  「{f}」出现在 {len(uniq)} 个不同行 / 共 {len(hits)} 行，其中做韵脚 {rhyme_n} 行")
            for _k, (l, n) in uniq.items():
                mark = "韵脚" if (rhyme_of(eng, l) or (None,))[0] == f else "句中"
                times = f" ×{n}" if n > 1 else ""
                print(f"     [{mark}]{times} {l}")

    # ---- ⑥ 特征字 ----
    print("\n⑥ 粤语特征字")
    hits = [(ch, allc.count(ch)) for ch in sorted(CHECKED_CHARS) if ch in allc]
    if hits:
        print("  ", hits)
        warns.append(f"粤语特征字 {len(hits)} 种：{hits}（内地传播口径下应为 0）")
    else:
        print("   0 处  OK")

    # ---- ⑦ 段长 ----
    print("\n⑦ 段长上限")
    for name, ls in secs:
        k = section_kind(name)
        if k in ("intro", "instrumental"):
            print(f"  {name:14s} {len(ls)} 行  ({k}，不卡行数)")
            continue
        if k == "unknown":
            print(f"  {name:14s} {len(ls)} 行  (未知段型，未卡)")
            continue
        lim = limits.get(k, 6)
        ok = len(ls) <= lim
        print(f"  {name:14s} {len(ls)} 行  上限 {lim}  {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"{name} {len(ls)} 行超上限 {lim}")

    # ---- ⑧ 人味三指标 ----
    print("\n⑧ 人味三指标（对照六首 90 年代真人经典）")
    n_you, n_me = allc.count("你"), allc.count("我")
    ok1 = n_you > 0
    print(f"  ① 第二人称：「你」{n_you} / 「我」{n_me}  {'OK' if ok1 else 'FAIL(0)'}")
    if not ok1:
        fails.append("「你」0 次——没有第二个人就没有关系，只剩处境")
    else:
        print("       逐处：" + " / ".join(f"…{m}…" for m in re.findall(r".{0,4}你.{0,4}", allc)))

    dun = [(n, len([p for p in re.split(r"[　\s]+", l.strip()) if p]), l)
           for n, ls in secs for l in ls]
    cnt3 = [d for d in dun if d[1] >= 3]
    ok2 = len(cnt3) >= 2
    print(f"  ② 顿数：3 顿及以上 {len(cnt3)} 行  {'OK' if ok2 else 'FAIL(<2)'}")
    for n, k, l in cnt3:
        print(f"       {n:14s} {k} 顿  {l}")
    print(f"       其余 {len(dun) - len(cnt3)} 行为 2 顿")
    if not ok2:
        fails.append(f"3 顿行只有 {len(cnt3)} 行（需 ≥2）；全篇 2 顿＝骨架锁死")

    lens = [(n, len(clean(l)), l) for n, ls in secs for l in ls]
    mx = max(x[1] for x in lens)
    mn = min(x[1] for x in lens)
    adj = max(abs(lens[i][1] - lens[i + 1][1]) for i in range(len(lens) - 1)) if len(lens) > 1 else 0
    ok3 = adj >= 4
    print(f"  ③ 单行字数：max {mx} / min {mn} / 极差 {mx-mn} / 相邻最大差 {adj}  {'OK' if ok3 else 'FAIL(<4)'}")
    for i in range(len(lens) - 1):
        if lens[i][1] >= 12 and lens[i][1] - lens[i + 1][1] >= 4:
            print(f"       {lens[i][0]} 满行 {lens[i][1]} 字 → 下一行 {lens[i+1][1]} 字（差 {lens[i][1]-lens[i+1][1]}）")
    if not ok3:
        fails.append(f"相邻行字数最大差 {adj} < 4——全篇等比，没有一个字是重的")

    # ---- ⑨ 回比 ----
    if args.compare:
        print("\n⑨ 交付文本回比")
        other = parse(args.compare)
        a = [clean(l) for _, ls in secs for l in ls]
        b = [clean(l) for _, ls in other for l in ls]
        print(f"  本稿 {len(a)} 行 / 对方 {len(b)} 行")
        if a == b:
            print("  逐行逐字一致  OK")
        else:
            fails.append("两文件行内容不一致")
            for i in range(max(len(a), len(b))):
                x = a[i] if i < len(a) else "(缺)"
                y = b[i] if i < len(b) else "(缺)"
                if x != y:
                    print(f"   第{i+1}行  本稿: {x}")
                    print(f"              对方: {y}")

    # ---- 汇总 ----
    print("\n" + "=" * 68)
    print(f"总段数 {len(secs)} / 总行数 {len(lens)} / 折叠后独立行 {len(folded)} / 总字数 {len(allc)}")
    print(f"注音：override {eng.override_hits() or '无'} | S2T 转换 {len(eng.s2t_hits())} 字")
    print(f"韵脚：平 {sum(1 for _, _, _, t in folded if t in FLAT_TONES)}"
          f" / 升 {sum(1 for _, _, _, t in folded if t in RISING_TONES)}"
          f" / 入 {sum(1 for _, _, f, _ in folded if is_checked(f))}")
    if fails:
        print(f"\nFAIL x{len(fails)}")
        for f in fails:
            print("   -", f)
    else:
        print("\nALL PASS")
    if warns:
        print(f"\nWARN x{len(warns)}（阈值标记 / 需人判断）")
        for w in warns:
            print("   -", w)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
