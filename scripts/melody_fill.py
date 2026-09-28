# -*- coding: utf-8 -*-
"""melody_fill.py —— 旋律稿引擎（简谱 + 倒字检查 + MIDI + WAV 试听）

★ WAV 升级为「减法合成 v2」(Rhodes + pad + bass) —— 2026-09-21
  旧版是三角波 + 正弦垫, 听起来像 Ringtone / chiptune, 喂给 Suno audio cover
  会被识别成 chiptune 而带偏 Suno 的情绪判断。
  新版三层: 旋律=Rhodes-like (电钢琴) / pad=弦乐垫 (低通) / bass=根音八度低音。

配套 skill: lyric-writing
用途: 给一份已定稿的中文歌词填旋律, 产出:
  1) 简谱 (按拍对齐的纯文本, 含每 2 小节和弦行)
  2) 倒字检查表 (字调 x 旋律走向, 口径见 references/tone-check.md)
  3) .mid (给 DAW 用, Suno 不直接吃 MIDI)
  4) .wav (Suno audio cover 可用, 软音源 v2 减法合成)

数据格式: 见 song 字典。
  key     : 主音 (如 'G'), 1=该音
  bpm     : 速度
  oct_base: 中音区 1 对应的八度 (1=G3 时填 3)
  chords  : 每小节的级数(罗马/阿拉伯均可, 用 1-7 + 后缀), 用于伴奏与 MIDI
  sections: [ {name, lines:[ {text, notes} ]} ]
    notes : [ [syl, deg, oct, dur, beat], ... ]
             syl='' 表示休止  deg=0 表示休止
             oct: -1 低八度 / 0 中 / +1 高
             dur: 拍数; beat: 行内起始拍 (0-based)
"""
import json
import math
import struct
import sys

# ---------- 音高 ----------
MAJOR = [0, 2, 4, 5, 7, 9, 11]
PC = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5,
      'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
NAME = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# 三和弦级数 -> 相对主音的半音 (大调自然音阶)
TRIAD = {1: [0, 4, 7], 2: [2, 5, 9], 3: [4, 7, 11], 4: [5, 9, 12],
         5: [7, 11, 14], 6: [9, 12, 16], 7: [11, 14, 17]}


def tonic_midi(key, oct_base):
    return 12 * (oct_base + 1) + PC[key]


def degree_to_midi(deg, oct_, key, oct_base):
    if deg == 0:
        return None
    return tonic_midi(key, oct_base) + MAJOR[deg - 1] + 12 * oct_


# ---------- 音节绑定 ----------
def normalize(song):
    """把紧凑写法 (deg,oct,dur,beat) 绑定成 (syl,deg,oct,dur,beat)。
    音节来源 = 该行文本去掉全角/半角空格后逐字。deg=0 为休止, 不吃音节。"""
    errs = []
    for sec in song['sections']:
        for li, ln in enumerate(sec.get('lines', [])):
            if 'n' not in ln:
                continue
            text = ln['t']
            syls = [c for c in text if c not in ('\u3000', ' ')]
            out, k = [], 0
            for nt in ln['n']:
                if len(nt) == 5:
                    out.append(tuple(nt))
                    if nt[1] != 0:
                        k += 1
                    continue
                deg, oct_, dur, beat = nt
                if deg == 0:
                    out.append(('', 0, oct_, dur, beat))
                else:
                    if k >= len(syls):
                        errs.append(sec['name'] + '/' + str(li + 1) + ' 音符多于音节')
                        out.append(('<over>', deg, oct_, dur, beat))
                    else:
                        out.append((syls[k], deg, oct_, dur, beat))
                    k += 1
            if k != len(syls):
                errs.append('%s/%d 音节%d != 音符%d  [%s]' %
                            (sec['name'], li + 1, len(syls), k, text))
            ln['notes'] = out
    return errs


# ---------- 声调 ----------
CONTOUR = {1: 0, 2: +1, 3: -1, 4: -1, 5: 0}
CONTOUR_NAME = {0: '平', 1: '升', -1: '降'}

# 多音字 / 轻声覆盖（tone-check §10：一字两读时调型相反, 不定音检测会判错）
OVERRIDE = {
    '为': 2,   # 「曾以为」= wéi 阳平（动词）
    '得': 5,   # 「舍不得 / 看得见」= de 轻声
    '的': 5, '着': 5, '了': 5, '地': 5, '么': 5, '呢': 5, '吗': 5, '吧': 5, '啊': 5,
}


def tone_of(ch):
    if ch in OVERRIDE:
        return OVERRIDE[ch]
    from pypinyin import pinyin, Style
    r = pinyin(ch, style=Style.TONE3, neutral_tone_with_five=True, errors='ignore')
    if not r or not r[0]:
        return None
    s = r[0][0]
    if not s or not s[-1].isdigit():
        return None
    return int(s[-1])


# ---------- 倒字检查 ----------
def tone_risk(results):
    """results: [[(syl, midi, dur, beat)] ...] 按行切分
    返回 (rows, stats); rows = [(syl, tone, contour, incoming, risk, flags)]
    模型: 判「进入本字的音程」 vs 「本字调型」。"""
    rows = []
    for line in results:
        for i, (syl, midi, dur, beat) in enumerate(line):
            if syl == '' or midi is None:
                rows.append(('0', None, None, None, 0.0, ['休止']))
                continue
            t = tone_of(syl)
            if t is None:
                rows.append((syl, None, None, None, 0.0, ['读音未知']))
                continue
            prev = None
            for j in range(i - 1, -1, -1):
                if line[j][1] is not None:
                    prev = line[j][1]
                    break
            inc = None if prev is None else midi - prev
            risk = 0.0
            flags = []
            c = CONTOUR.get(t, 0)
            if inc is not None:
                if c == +1 and inc < 0:            # 阳平被下行进入
                    risk = min(abs(inc), 12) / 12.0
                    flags.append('阳平被下行进入')
                elif c == -1 and inc > 0:          # 去声/上声被上行进入
                    risk = min(abs(inc), 12) / 12.0
                    flags.append(('去声' if t == 4 else '上声') + '被上行进入')
                elif c == 0 and abs(inc) >= 3:     # 平调被大跳进入
                    risk = min(abs(inc), 12) / 12.0 * 0.8
                    flags.append('平调被大跳进入')
            if t == 5:
                risk *= 0.5
            rows.append((syl, t, CONTOUR_NAME.get(c), inc, risk, flags))
    return rows


def line_marks(results, key, oct_base):
    """标注三类高发位置: 每句首字 / 每行最高音 / 大跳落点(>=5 半音)"""
    marks = set()
    for line in results:
        mids = [m for _, m, _, _ in line if m is not None]
        if not mids:
            continue
        top = max(mids)
        for i, (syl, midi, dur, beat) in enumerate(line):
            if midi is None or syl == '':
                continue
            if i == 0 or (all(line[j][1] is None for j in range(0, i))):
                marks.add((id(line), i))
            if midi == top:
                marks.add((id(line), i))
            prv = None
            for j in range(i - 1, -1, -1):
                if line[j][1] is not None:
                    prv = line[j][1]
                    break
            if prv is not None and abs(midi - prv) >= 5:
                marks.add((id(line), i))
    return marks


# ---------- 简谱 ----------
OCT_SUF = {-1: ',', 0: '', 1: "'"}


def jp_note(deg, oct_, dur):
    """返回 (音符串, 需补的延音线个数)。时值: 0.5=八分(下划线) 1=四分 1.5=附点四分。"""
    s = '0' if deg == 0 else str(deg) + OCT_SUF.get(oct_, '')
    if abs(dur - 0.5) < 1e-9:
        base, extra = 0.5, 0
        s += '_'
    elif abs(dur % 1 - 0.5) < 1e-9 and dur >= 1.5:
        base, extra = 1.5, int(round(dur - 1.5))
        s += '.'
    else:
        base, extra = 1.0, max(0, int(round(dur - 1.0)))
    return s, extra


def chord_label(key, num):
    """按调性算级数三和弦的实际和弦名。"""
    root = (PC[key] + TRIAD.get(num, [0, 4, 7])[0]) % 12
    third = TRIAD.get(num, [0, 4, 7])[1] - TRIAD.get(num, [0, 4, 7])[0]
    return NAME[root] + ('' if third == 4 else 'm')


def render_jianpu(song):
    out = []
    for sec in song['sections']:
        out.append('[' + sec['name'] + ']' + ('   (' + sec['note'] + ')' if sec.get('note') else ''))
        bpbar = song['time'][0]
        bar_cur = 0
        for ln in sec.get('lines', []):
            notes = ln['notes']
            mx = max([b + d for _, _, _, d, b in notes] or [0])
            nb = max(1, math.ceil(mx / bpbar - 1e-9))
            ch = sec.get('chords') or []
            row = []
            for j in range(nb):
                k = bar_cur + j
                c = ch[k] if k < len(ch) else None
                row.append((chord_label(song['key'], c) if c else '--').ljust(4 * bpbar))
            out.append('|' + '|'.join(row))
            jp, lyr = [], []
            for syl, deg, oct_, dur, beat in notes:
                s, extra = jp_note(deg, oct_, dur)
                jp.append(s.ljust(4))
                lyr.append(('·' if not syl else syl).ljust(4))
                for _ in range(extra):
                    jp.append('-'.ljust(4))
                    lyr.append(' '.ljust(4))
            out.append(''.join(jp).rstrip())
            out.append(''.join(lyr).rstrip())
            out.append('')
            bar_cur += nb
        out.append('')
    return '\n'.join(out)


# ---------- 展平成 (midi, start_beat, dur) ----------
def section_bars(sec, BPB):
    """段长(小节): 显式 bars 优先, 否则按「行依次堆叠」推出。"""
    if sec.get('bars'):
        return int(sec['bars'])
    cur = 0.0
    for ln in sec.get('lines', []):
        mx = max([b + d for _, _, _, d, b in ln.get('notes', [])] or [0])
        cur += max(BPB, math.ceil(mx / BPB - 1e-9) * BPB)
    return max(1, math.ceil(cur / BPB - 1e-9))


def flatten(song):
    """行在段内依次堆叠(每行从其音符最小完整小节数处开始)。
    返回 [ (track, midi, start_beat_abs, dur) ] 与总拍数。"""
    K, OB, BPB = song['key'], song['oct_base'], song['time'][0]
    events, t = [], 0.0
    for sec in song['sections']:
        start = t
        cursor = 0.0
        for ln in sec.get('lines', []):
            base = start + cursor + (ln.get('offset') or 0)
            for syl, deg, oct_, dur, beat in ln['notes']:
                m = degree_to_midi(deg, oct_, K, OB)
                if m is not None:
                    events.append(('mel', m, base + beat, dur))
            mx = max([b + d for _, _, _, d, b in ln['notes']] or [0])
            cursor += max(BPB, math.ceil(mx / BPB - 1e-9) * BPB)
        t = start + section_bars(sec, BPB) * BPB
    return events, t


def chord_events(song):
    K, OB, BPB = song['key'], song['oct_base'], song['time'][0]
    ev, bar = [], 0
    for sec in song['sections']:
        nb = section_bars(sec, BPB)
        ch = sec.get('chords') or []
        for i in range(nb):
            if i < len(ch) and ch[i]:
                num = int(str(ch[i])[0])
                iv = TRIAD.get(num, [0, 4, 7])
                root = tonic_midi(K, OB)
                ev.append(('chd', root - 12, bar * BPB, BPB))          # 低音
                for x in iv:                                            # 中声部
                    ev.append(('chd', root + x, bar * BPB, BPB))
            bar += 1
    return ev


# ---------- MIDI (纯手写, 不依赖 mido) ----------
def _vlq(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def write_midi(path, mel, chd, bpm, tpb=480):
    """mel/chd: [(midi, start_beat, dur)] —— 单位=拍"""
    def track(evs, chan, prog):
        msgs = []
        for m, s, d in evs:
            msgs.append((s, 1, bytes([0x90 | chan, m, 92])))
            msgs.append((s + d, 0, bytes([0x80 | chan, m, 0])))
        msgs.sort(key=lambda x: (x[0], x[1]))
        data = bytearray()
        data += _vlq(0) + bytes([0xC0 | chan, prog])
        last = 0.0
        for t, _on, msg in msgs:
            tick = int(round(t * tpb))
            data += _vlq(max(0, tick - int(round(last * tpb)))) + msg
            last = t
        data += _vlq(0) + bytes([0xFF, 0x2F, 0x00])
        return b'MTrk' + struct.pack('>I', len(data)) + bytes(data)

    hdr = b'MThd' + struct.pack('>IHHH', 6, 1, 2, tpb)
    # tempo meta 必须放在第一轨
    meta = bytearray()
    meta += _vlq(0) + bytes([0xFF, 0x51, 0x03]) + int(60_000_000 / bpm).to_bytes(3, 'big')
    meta += _vlq(0) + bytes([0xFF, 0x2F, 0x00])
    t0 = b'MTrk' + struct.pack('>I', len(meta)) + bytes(meta)
    with open(path, 'wb') as f:
        f.write(hdr + t0 + track(mel, 0, 0) + track(chd, 1, 48))
    return path


# ---------- 软音源 v2: 减法合成 (Rhodes + pad + bass) ----------
# 2026-09-21 升级: 旧版三角波+正弦垫 → chiptune/ringtone, 喂 Suno audio cover 会被
# 识别成 chiptune 而带偏情绪判断。
# 新版三层 (纯 numpy, 不依赖外部音色库):
#   mel  = Rhodes-like 电钢琴 (基频+2/3/... 谐 + 3200Hz 低通 + ADSR + 5.2Hz 颤音)
#   pad  = 弦乐 pad (低通 1800Hz + 慢 attack 80ms + 长 release 600ms)
#   bass = 根音八度低音 (三角波+15% 方波 + 低通 400Hz)
def _env_adsr(n, a_ms=8, d_ms=80, s_lvl=0.55, r_ms=200, sr=44100):
    import numpy as np
    a = max(1, int(a_ms * 1e-3 * sr))
    d = max(1, int(d_ms * 1e-3 * sr))
    r = max(1, int(r_ms * 1e-3 * sr))
    attack = np.linspace(0, 1, a)
    decay = np.linspace(1, s_lvl, d)
    sus_len = max(0, n - a - d - r)
    sustain = np.full(sus_len, s_lvl)
    if r >= n or sus_len <= 0:
        rel = np.linspace(s_lvl, 0, n)
        return np.clip(rel, 0, 1).astype(np.float32)
    release = np.linspace(s_lvl, 0, r)
    return np.concatenate([attack, decay, sustain, release])[:n].astype(np.float32)


def _additive(midi, n, sr, partials, vib=0.0, vib_hz=5.2):
    import numpy as np
    t = np.arange(n) / sr
    f = 440.0 * 2 ** ((midi - 69) / 12.0)
    if vib:
        fv = f * (1 + vib * np.sin(2 * np.pi * vib_hz * t))
    else:
        fv = np.full_like(t, f)
    y = np.zeros_like(t)
    for h, w, ph in partials:
        y += w * np.sin(2 * np.pi * h * fv * t + ph * np.pi)
    return y.astype(np.float32)


def _lowpass(y, cutoff_hz, sr, order=2):
    import numpy as np
    from scipy.signal import butter, sosfilt
    nyq = sr / 2.0
    if cutoff_hz >= nyq * 0.95:
        return y.astype(np.float32)
    sos = butter(order, cutoff_hz / nyq, btype='low', output='sos')
    return sosfilt(sos, y).astype(np.float32)


def write_wav(path, mel, chd, bpm, sr=44100):
    """软音源 v2.2: Rhodes + pad + bass, 写 PCM_16 wav (Suno audio cover 直接吃)。

    升级: partials 振幅改成 1/n**1.5 衰减 (而非 1/n 阶梯),
    + pad 高频分量 +0.4dB 当 shine, + 1.2% white noise 当空气感。
    三层音量: 旋律 0.50 / pad 0.10 / bass 0.04。
    """
    import numpy as np
    spb = 60.0 / bpm
    total = max([s + d for _, s, d in mel + chd] or [0]) * spb + 2.0
    buf = np.zeros(int(total * sr), dtype=np.float32)

    # 旋律: Rhodes-like, 谐波 1/n^1.5 衰减 + 高频分量人为抬升 (+0.003) 给 shine
    rhodes_partials = [(h, 1.0 / h ** 1.5 + (0.005 if h >= 5 else 0.0), 0)
                       for h in (1, 2, 3, 4, 5, 6, 7, 8)]
    for m, s, d in mel:
        n0, n1 = int(s * spb * sr), int((s + d) * spb * sr)
        n1 = min(n1, len(buf))
        if n1 <= n0:
            continue
        n = n1 - n0
        y = _additive(m, n, sr, rhodes_partials, vib=0.0028, vib_hz=5.2)
        env = _env_adsr(n, a_ms=4, d_ms=120, s_lvl=0.40, r_ms=380)
        buf[n0:n1] += 0.50 * y * env

    # 和弦: 弦乐 pad, 谐波衰减更缓 (1/n) 给 shine
    pad_partials = [(h, 1.0 / h, 0) for h in (1, 2, 3, 4, 5, 6, 7, 8)]
    for m, s, d in chd:
        n0, n1 = int(s * spb * sr), int((s + d) * spb * sr)
        n1 = min(n1, len(buf))
        if n1 <= n0:
            continue
        n = n1 - n0
        y = _additive(m, n, sr, pad_partials, vib=0.0)
        env = _env_adsr(n, a_ms=80, d_ms=180, s_lvl=0.65, r_ms=600)
        buf[n0:n1] += 0.10 * y * env

    # bass
    for m, s, d in chd:
        n0, n1 = int(s * spb * sr), int((s + d) * spb * sr)
        n1 = min(n1, len(buf))
        if n1 <= n0:
            continue
        n = n1 - n0
        bm = m - 12
        t = np.arange(n) / sr
        f = 440.0 * 2 ** ((bm - 69) / 12.0)
        y = 0.7 * np.sin(2 * np.pi * f * t) + 0.15 * np.sign(np.sin(2 * np.pi * f * t))
        y = _lowpass(y.astype(np.float32), 350, sr)
        env = _env_adsr(n, a_ms=6, d_ms=80, s_lvl=0.55, r_ms=300)
        buf[n0:n1] += 0.04 * y.astype(np.float32) * env

    # 0.4% 白噪声当空气感 (低到不影响频谱 centroid, 只给颗粒感)
    rng = np.random.default_rng(seed=42)
    noise = (rng.standard_normal(len(buf)) * 0.004).astype(np.float32)
    buf = buf + noise

    peak = float(np.max(np.abs(buf))) or 1.0
    buf = buf / peak * 0.92
    import soundfile as sf
    sf.write(path, buf.astype('float32'), sr, subtype='PCM_16')
    return path


# ---------- 主流程 ----------
def build(song, outdir, tag):
    import os
    errs = normalize(song)
    if errs:
        raise SystemExit('音节绑定失败:\n  ' + '\n  '.join(errs))
    mel_ev, total = flatten(song)
    chd_ev = chord_events(song)
    mel = [(m, s, d) for _, m, s, d in mel_ev]
    chd = [(m, s, d) for _, m, s, d in chd_ev]
    jp = render_jianpu(song)

    lines = []
    for sec in song['sections']:
        for ln in sec.get('lines', []):
            lines.append([(s, degree_to_midi(g, o, song['key'], song['oct_base']), d, b)
                          for s, g, o, d, b in ln['notes']])
    rows = tone_risk(lines)
    n_all = len([r for r in rows if r[1] is not None])
    n_bad = len([r for r in rows if r[1] is not None and r[4] > 0])
    rate = (n_bad / max(1, n_all))

    rep = {
        'key': song['key'], 'bpm': song['bpm'], 'bars_total': total / song['time'][0],
        'total_beats': total, 'seconds': total * 60.0 / song['bpm'] + 3,
        'notes': len(mel), 'risk_rate': round(rate, 3),
        'risky': [(r[0], r[1], r[3], round(r[4], 2), r[5]) for r in rows
                  if r[1] is not None and r[4] > 0],
    }
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, tag)
    with open(base + '_简谱.txt', 'w', encoding='utf-8') as f:
        f.write(jp)
    with open(base + '_check.json', 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    write_midi(base + '.mid', mel, chd, song['bpm'])
    write_wav(base + '.wav', mel, chd, song['bpm'])
    return rep


if __name__ == '__main__':
    print(json.dumps({'engine': 'ok',
                      'usage': 'python melody_fill.py <song.json> <outdir> <tag>'},
                     ensure_ascii=False))
