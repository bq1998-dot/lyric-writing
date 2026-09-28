# -*- coding: utf-8 -*-
"""verify_zh.py —— 中文（普通话）歌词通用校验器，口径对齐 verify_yue.py。

九项检查：
  ① 逐行字数 / 段内极差（含"呼吸点"判定）
  ② 韵脚（末字）十三辙归属 / 声调（上声韵脚 WARN）
  ③ 上声连用（3+3，FAIL） / 三连上声（WARN）—— 与粤语脚本同口径：**全角/半角空格不隔断相邻性**
  ④ 韵脚复押（相同文本的行折叠成一遍后统计）
  ⑤ 焦点字渗透（--focus，看某字是否只落在句中、从不占韵脚）
  ⑥ 粤语特征字（普通话稿应为 0）
  ⑦ 段长上限（按曲风 + BPM 感知）
  ⑧ 人味三指标（你>0 / ≥2 行 3 顿 / 相邻行字数差 ≥4）
  ⑨ 交付文本回比（--compare）

退出码：有 FAIL → 1，否则 0
用法：
  python verify_zh.py 歌词.txt
  python verify_zh.py 歌词.txt --focus 说
  python verify_zh.py 歌词.txt --genre ballad --bpm 78
  python verify_zh.py 歌词.txt --compare 交付版.txt
"""
import argparse
import os
import re
import sys
from collections import Counter, OrderedDict

from pypinyin import pinyin, Style

# ---------------- 十三辙 映射 ----------------
RHYME_MAP = {
    'a': '发花', 'ia': '发花', 'ua': '发花',
    'o': '梭波', 'e': '梭波', 'uo': '梭波', 'io': '梭波', 'ê': '梭波',
    'ie': '乜斜', 've': '乜斜',
    'i': '一七', 'v': '一七', 'er': '一七',
    'u': '姑苏',
    'ai': '怀来', 'uai': '怀来',
    'ei': '灰堆', 'ui': '灰堆', 'uei': '灰堆',
    'ao': '遥条', 'iao': '遥条',
    'ou': '由求', 'iu': '由求', 'iou': '由求',
    'an': '言前', 'ian': '言前', 'uan': '言前', 'van': '言前',
    'en': '人辰', 'in': '人辰', 'un': '人辰', 'uen': '人辰', 'vn': '人辰',
    'ang': '江阳', 'iang': '江阳', 'uang': '江阳',
    'eng': '中东', 'ing': '中东', 'ong': '中东', 'iong': '中东', 'ueng': '中东',
}

# 多音字人工覆写（按语境定音，值 = (韵母, 声调)）
OVERRIDE = {
    '的': ('e', 5), '了': ('e', 5), '着': ('e', 5), '们': ('en', 5), '得': ('e', 5),
    '不': ('u', 5),   # 去声前的"不"常读轻声；本稿用于避免 3+3 误判，按轻声处理
    '过': ('uo', 4), '差': ('a', 4),   # 只差 → chà
    '还': ('ai', 2),  # 还是/还在 → hái
    '曾': ('eng', 2),  # 曾以为 → céng
    '为': ('ei', 2),  # 曾以为 → wéi
    '舍': ('e', 3),   # 舍不得 → shě
    '说': ('uo', 1),  # 说出来 → shuō
    '那': ('a', 4), '这': ('e', 4),
    '血': ('ve', 4),
}

TRIM = ' \t　、。，！？；：,.!?;:""\'\'（）()《》…—-'


def clean(t):
    """去掉全角/半角空白——与 verify_yue.py 同口径：空格不隔断相邻性。"""
    return re.sub(r"[　\s]", "", t)


def tone_of(ch):
    """返回 (韵母, 声调)；y 等非汉字返回 None。"""
    if ch in OVERRIDE:
        return OVERRIDE[ch]
    r = pinyin(ch, style=Style.FINALS_TONE3, errors='ignore')
    if not r or not r[0]:
        return None
    f = r[0][0]
    m = re.match(r'^(.*?)(\d)$', f)
    if not m:
        return None
    fin = m.group(1).replace('ü', 'v')
    return (fin, int(m.group(2)))


def rhyme_of(line):
    """行末字（去尾部标点）-> (字, 辙名, 韵母, 声调) 或 None"""
    c = clean(line).rstrip(TRIM)
    if not c:
        return None
    ch = c[-1]
    r = tone_of(ch)
    if not r:
        return None
    fin, tone = r
    return (ch, RHYME_MAP.get(fin, f'?{fin}'), fin, tone)


def is_sec(l):
    return bool(re.match(r'^\[.*\]$', l.strip()))


LIMITS = {'verse': 6, 'chorus': 6, 'bridge': 4, 'pre': 4, 'outro': 4, 'intro': 99, 'instrumental': 99}


def sec_kind(name):
    n = name.lower()
    if n.startswith('pre'): return 'pre'
    if n.startswith('verse'): return 'verse'
    if n.startswith('chorus') or n.startswith('final'): return 'chorus'
    if n.startswith('bridge'): return 'bridge'
    if n.startswith('outro'): return 'outro'
    if n.startswith('intro'): return 'intro'
    if n.startswith('instrument') or n.startswith('solo'): return 'instrumental'
    if n.startswith('post'): return 'chorus'
    return 'verse'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--genre', default='ballad')
    ap.add_argument('--bpm', type=float, default=None)
    ap.add_argument('--focus', action='append', default=[])
    ap.add_argument('--compare', default=None)
    args = ap.parse_args()

    txt = open(args.path, encoding='utf-8').read()
    lines = txt.replace('\r\n', '\n').split('\n')

    secs, cur, curlines = [], None, []
    for l in lines:
        s = l.strip()
        if not s:
            continue
        if is_sec(s):
            if cur:
                secs.append((cur, curlines))
            cur, curlines = s[1:-1], []
        elif cur is not None:
            curlines.append(s)
    if cur:
        secs.append((cur, curlines))

    fails, warns = [], []

    print('=' * 68)
    print(f'文件: {args.path}')
    lim = dict(LIMITS)
    if args.bpm is not None and args.bpm < 80:
        lim['verse'] = 4
    print(f'曲风: {args.genre}   BPM: {args.bpm if args.bpm else "-"}   段长上限: {lim}')
    print('=' * 68)

    # ---- ① 逐行字数 / 段内极差 ----
    print('\n① 逐行字数 / 段内极差')
    for name, ls in secs:
        if not ls:
            print(f'  {name:<15} (无词)')
            continue
        cnt = [len(clean(l).rstrip(TRIM)) for l in ls]
        spread = max(cnt) - min(cnt)
        flags = []
        for i in range(len(cnt) - 1):
            if abs(cnt[i] - cnt[i + 1]) >= 4 and cnt[i] > cnt[i + 1]:
                flags.append(f'呼吸点 @ 第{i+1}行→第{i+2}行（差{abs(cnt[i]-cnt[i+1])}）')
        mark = 'OK' if spread <= 2 else ('呼吸点' if flags else '偏大')
        print(f'  {name:<15} {cnt}  极差={spread}  {mark}' + ('  ' + ' / '.join(flags) if flags else ''))
        if spread > 2 and not flags:
            warns.append(f'{name} 段内极差 {spread}，且不存在「长→短」相邻对（需处理）')

    # ---- ② 韵脚 ----
    print('\n② 韵脚（末行字）十三辙 / 声调')
    allrh = []
    for name, ls in secs:
        if not ls:
            continue
        rs = [rhyme_of(l) for l in ls]
        rs = [r for r in rs if r]
        if not rs:
            continue
        for r in rs:
            tag = '上声!' if r[3] == 3 else ('轻' if r[3] == 5 else 'OK')
            print(f'  {name:<15} …{r[0]}  {r[1]:<4} 调{r[3]}  {tag}')
            if r[3] == 3:
                warns.append(f'{name} 韵脚「{r[0]}」是上声(3)，不可落长音（无旋律时属风险）')
        c = Counter(r[1] for r in rs)
        top, n = c.most_common(1)[0]
        ok = 'OK' if n == len(rs) else '段内跑辙!'
        print(f'    → 段内主辙 {top} ({n}/{len(rs)}={n*100//len(rs)}%)  其他: {[k for k in c if k != top] or "无"}  {ok}')
        if n != len(rs):
            fails.append(f'{name} 段内跑辙：{dict(c)}')
        allrh.extend(rs)

    # ---- ③ 上声连用 ----
    print('\n③ 上声连用（相邻 3+3） / 三连上声')
    n_adj = 0
    for name, ls in secs:
        for i, l in enumerate(ls):
            c = clean(l)
            to = [(ch, tone_of(ch)) for ch in c]
            miss = [ch for ch, t in to if t is None]
            if miss:
                warns.append(f'{name} 第{i+1}行有未注音字 {miss}')
                continue
            for k in range(len(to) - 1):
                if to[k][1][1] == 3 and to[k + 1][1][1] == 3:
                    n_adj += 1
                    fails.append(f'{name} 第{i+1}行 上声连用：「{to[k][0]}{to[k+1][0]}」')
            for k in range(len(to) - 2):
                if all(to[k + j][1][1] == 3 for j in range(3)):
                    warns.append(f'{name} 第{i+1}行 三连上声：「{to[k][0]}{to[k+1][0]}{to[k+2][0]}」')
    print(f'  上声连用 {n_adj} 处' + ('（全部已列入 FAIL）' if n_adj else '  OK'))

    # ---- ④ 复押 ----
    print('\n④ 韵脚复押（相同文本的行折叠成一遍后统计）')
    seen, folded = OrderedDict(), []
    for name, ls in secs:
        for l in ls:
            key = clean(l)
            if key in seen:
                continue
            seen[key] = True
            rr = rhyme_of(l)
            if rr:
                folded.append(rr)
    cnt = Counter(f[0] for f in folded)
    print(f'  折叠后 {len(folded)} 位，不同字 {len(cnt)} 个')
    print('  序列: ' + ' '.join(f'{c}{m}{t}' for c, m, f, t in folded))
    for ch, n in cnt.items():
        if n > 2:
            fails.append(f'韵脚「{ch}」出现 {n} 次（上限 2 次，且须隔开整段）')
    print('  单字最多 ' + str(max(cnt.values()) if cnt else 0) + ' 次' + ('  OK' if cnt and max(cnt.values()) <= 2 else ''))

    # ---- ⑤ 焦点字 ----
    if args.focus:
        print('\n⑤ 焦点字渗透')
        for fch in args.focus:
            inmid, atrh = 0, 0
            where = []
            for name, ls in secs:
                for l in ls:
                    c = clean(l)
                    if fch in c:
                        rh = rhyme_of(l)
                        if rh and rh[0] == fch:
                            atrh += 1; where.append(f'[韵脚] {l}')
                        else:
                            inmid += 1; where.append(f'[句中] {l}')
            print(f'  「{fch}」出现在 {inmid+atrh} 个不同的行，其中做韵脚 {atrh} 行')
            for w in where:
                print(f'     {w}')

    # ---- ⑥ 粤语特征字 ----
    print('\n⑥ 粤语特征字（普通话稿应为 0）')
    YUE = set('唔嘅咗係冇咁喺佢哋睇嘢俾')
    hits = [(name, i + 1, ch) for name, ls in secs for i, l in enumerate(ls) for ch in clean(l) if ch in YUE]
    if hits:
        for name, ln, ch in hits:
            fails.append(f'{name} 第{ln}行出现粤语特征字「{ch}」')
    print(f'   {len(hits)} 处' + ('  OK' if not hits else ''))

    # ---- ⑦ 段长 ----
    print('\n⑦ 段长上限')
    for name, ls in secs:
        k = sec_kind(name)
        cap = lim.get(k, 6)
        n = len(ls)
        st = 'OK' if n <= cap else '超限!'
        if k in ('intro', 'instrumental'):
            print(f'  {name:<15} {n} 行  ({k}，不卡行数)')
        else:
            print(f'  {name:<15} {n} 行  上限 {cap}  {st}')
            if n > cap:
                fails.append(f'{name} 段长 {n} 行 > 上限 {cap}')

    # ---- ⑧ 人味三指标 ----
    print('\n⑧ 人味三指标（对照六首 90 年代真人经典）')
    body = [clean(l) for _, ls in secs for l in ls]
    raw_body = [l for _, ls in secs for l in ls]   # 保留行内全角空格（换气标记）
    n_ni = sum(l.count('你') for l in body)
    n_wo = sum(l.count('我') for l in body)
    print(f'  ① 第二人称：「你」{n_ni} / 「我」{n_wo}  ' + ('OK' if n_ni > 0 else 'FAIL（你=0）'))
    if n_ni == 0:
        fails.append('人味① 第二人称「你」为 0')
    d3 = [(name, i + 1, l) for name, ls in secs for i, l in enumerate(ls)
          if len([p for p in re.split(r'[　\s]+', l.strip()) if p]) >= 3]
    print(f'  ② 顿数：3 顿及以上 {len(d3)} 行  ' + ('OK' if len(d3) >= 2 else 'FAIL（<2 行）'))
    if len(d3) < 2:
        fails.append(f'人味② 3 顿行仅 {len(d3)} 行（门槛 2）')
    for name, i, l in d3:
        print(f'       {name:<15} {len([p for p in re.split(r"[　\s]+", l.strip()) if p])} 顿  {l}')
    lens = [len(clean(l)) for _, ls in secs for l in ls]
    mx = max(lens) if lens else 0
    mn = min(lens) if lens else 0
    admax = max([abs(lens[i] - lens[i + 1]) for i in range(len(lens) - 1)] or [0])
    print(f'  ③ 单行字数：max {mx} / min {mn} / 极差 {mx-mn} / 相邻最大差 {admax}  ' + ('OK' if admax >= 4 else 'FAIL'))
    if admax < 4:
        fails.append(f'人味③ 相邻行字数最大差仅 {admax}（门槛 4）')

    print('\n' + '=' * 68)
    print(f'总段数 {len(secs)} / 总行数 {len(body)} / 折叠后独立行 {len(folded)} / 总字数 {sum(lens)}')
    print(f'韵脚：共 {len(allrh)} 位')

    # ---- ⑨ 回比 ----
    if args.compare:
        print('\n⑨ 交付文本回比')
        other = open(args.compare, encoding='utf-8').read().replace('\r\n', '\n').split('\n')
        o_lines = [l.strip() for l in other if l.strip() and not is_sec(l.strip())]
        m_lines = raw_body
        print(f'  本稿 {len(m_lines)} 行 / 对方 {len(o_lines)} 行')
        if m_lines == o_lines:
            print('  逐行逐字一致  OK')
        else:
            fails.append('⑨ 交付文本与回比稿不一致')
            for i in range(max(len(m_lines), len(o_lines))):
                a = m_lines[i] if i < len(m_lines) else '<缺>'
                b = o_lines[i] if i < len(o_lines) else '<缺>'
                if a != b:
                    print(f'    第{i+1}行 本稿={a!r} 对方={b!r}')

    print()
    if fails:
        print(f'FAIL x{len(fails)}')
        for f in fails:
            print(f'   - {f}')
        print()
    if warns:
        print(f'WARN x{len(warns)}（阈值标记 / 需人判断）')
        for w in warns:
            print(f'   - {w}')
        print()
    print('ALL PASS' if not fails else 'HAS FAIL')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
