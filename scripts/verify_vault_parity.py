# -*- coding: utf-8 -*-
"""verify_vault_parity.py — 歌词交付双出口回比

用途：vault 里每首歌有两份交付件
  - ``歌词创作_<名>.md``  文档（含歌词代码块）
  - ``歌词创作_<名>.txt`` 纯段落标签版（直接粘 Suno Lyrics 框）
两者必须**逐行逐字一致**。md 里图省事写「（同上）」「略」是最高频的事故源。

用法：
    python scripts/verify_vault_parity.py "<vault 歌词目录>"          # 扫全目录
    python scripts/verify_vault_parity.py "<vault 歌词目录>" -n 歌名A -n 歌名B
退出码：0 = 全部一致；1 = 有 FAIL（可直接用于交付前门禁）。

判据：
  1. 逐行 ``==``，去行尾空白，**保留行内全角空格**（那是换气标记，不是排版噪声）。
  2. 挑块：只在**含段落标签**（``[Verse`` / ``[Chorus`` …）的代码块里挑，
     取**标签行最多**的那块；平手取最长。**不能只取第一个** ——
     交付文档通常有多个块（结构图 / 韵脚板 / 简谱 …），取第一个必然误报。
  3. 多个候选块 → 打 WARN 提示人工确认（挑错块会变成假 FAIL）。
  4. 两边都不含段落标签 → 判为「非歌词双出口」，SKIP，不误报。
  5. **每个 SKIP 都打印原因**，不做静默跳过 —— 静默跳过会让「跳过数」虚高而无人察觉。
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# md 里的代码块围栏：``` 或 ```text / ```txt / ```lyrics / ```md / ```markdown
FENCE = re.compile(r'^\s*```(?:text|txt|lyrics|md|markdown)?\s*$')

# 独立成行的段落标签
TAG_LINE = re.compile(r'^\s*\[[^\]]+\]\s*$')


def _all_blocks(md_text):
    """取出 md 里所有代码块，每个块是行列表。"""
    lines = md_text.replace('\r\n', '\n').split('\n')
    in_block = False
    blocks = []
    cur = []
    for ln in lines:
        if FENCE.match(ln):
            if not in_block:
                in_block, cur = True, []
                continue
            blocks.append(cur)
            in_block = False
            continue
        if in_block:
            cur.append(ln.rstrip())
    if in_block and cur:          # 围栏没闭合也收下，避免静默丢块
        blocks.append(cur)
    return blocks


def _tag_count(lines):
    """块里独立成行的段落标签有几行。"""
    return sum(1 for l in lines if TAG_LINE.match(l.strip()))


def extract_block(md_text):
    """挑出歌词代码块。返回 ``(块, 含标签的候选块数)``。

    判据：**段落标签行最多的那一块**；平手时取最长的一块；
    一块都没有标签时返回 ``(None, 0)``（调用方据此判「非歌词双出口」）。
    """
    blocks = _all_blocks(md_text)
    if not blocks:
        return None, 0
    cands = [b for b in blocks if _tag_count(b)]
    if not cands:
        return None, 0
    best = max(cands, key=lambda b: (_tag_count(b), len(b)))
    return best, len(cands)


def read_lines(path):
    txt = open(path, encoding='utf-8').read().replace('\r\n', '\n')
    return [l.rstrip() for l in txt.split('\n')]


def trim_tail(lines):
    """去掉尾部空行 —— .txt 通常以换行结尾，代码块通常不以空行结尾。"""
    out = list(lines)
    while out and not out[-1].strip():
        out.pop()
    return out


def check_one(md_path, txt_path):
    """返回 ``(status, msgs, warns)``，status ∈ {'OK','FAIL','SKIP'}。"""
    md_text = open(md_path, encoding='utf-8').read()
    block, n_cand = extract_block(md_text)
    b = trim_tail(read_lines(txt_path))
    warns = []

    if block is None:
        if _tag_count(b) == 0:
            return 'SKIP', ['两边都不含段落标签（非歌词双出口）'], warns
        return 'FAIL', ['md 里找不到含段落标签的代码块'], warns

    a = trim_tail(block)
    if _tag_count(a) == 0 and _tag_count(b) == 0:
        return 'SKIP', ['两边都不含段落标签（非歌词双出口）'], warns

    if n_cand > 1:
        warns.append(f'md 内有 {n_cand} 个含段落标签的代码块，已取标签最多的那块 —— 请人工确认')

    if a == b:
        return 'OK', [f'{len(a)} 行逐行逐字一致'], warns

    msgs = [f'行数 md {len(a)} / txt {len(b)}']
    n = 0
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else '<缺>'
        y = b[i] if i < len(b) else '<缺>'
        if x != y:
            n += 1
            msgs.append(f'  第{i+1}行 md={x!r}  txt={y!r}')
            if n >= 10:
                msgs.append('  …（只列前 10 处）')
                break
    return 'FAIL', msgs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('directory', help='歌词目录')
    ap.add_argument('-n', '--name', action='append', default=None,
                    help='只查某一首（不含「歌词创作_」前缀与扩展名）；可重复')
    args = ap.parse_args()

    d = args.directory
    if not os.path.isdir(d):
        print(f'目录不存在：{d}')
        return 1

    mds = sorted(f for f in os.listdir(d)
                 if f.startswith('歌词创作_') and f.endswith('.md'))
    if args.name:
        want = {f'歌词创作_{n}.md' for n in args.name}
        mds = [f for f in mds if f in want]

    if not mds:
        print('没找到可配对的 md（命名需为「歌词创作_<名>.md」）')
        return 1

    ok_cnt = fail_cnt = skip_cnt = 0
    fails, warned = [], []
    for md in mds:
        stem = md[:-3]                      # 去掉 .md
        txt = stem + '.txt'
        if not os.path.exists(os.path.join(d, txt)):
            print(f'SKIP  {stem}  （无同名 .txt，非双出口交付）')
            skip_cnt += 1
            continue

        status, msgs, warns = check_one(os.path.join(d, md), os.path.join(d, txt))
        if status == 'SKIP':
            print(f'SKIP  {stem}  （{msgs[0]}）')
            skip_cnt += 1
            continue
        if status == 'OK':
            print(f'OK    {stem}  {msgs[0]}')
            ok_cnt += 1
        else:
            print(f'FAIL  {stem}')
            for m in msgs:
                print(f'      {m}')
            fail_cnt += 1
            fails.append(stem)
        for w in warns:
            print(f'WARN  {stem}  {w}')
            warned.append(stem)

    print('-' * 68)
    print(f'一致 {ok_cnt} / 不一致 {fail_cnt} / 跳过 {skip_cnt}')
    if warned:
        print(f'WARN {len(warned)} 条（已逐条列出，需人工确认）')
    if fails:
        print('不一致清单：' + '、'.join(fails))
        print('HAS FAIL')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
