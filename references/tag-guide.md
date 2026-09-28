# Suno 标签：放哪些、放多少、怎么嵌

> 用途：`SKILL.md` 的「Suno 元标签」表讲**有哪些标签**，本文件讲**放多少才不过载**。
> 来源：节制规则与标签族索引吸收自 Apache-2.0 项目 `NuNaught/suno-songwriting-skill`
> 的 `references/lyric-tag-knowledge.md` 与 `references/structure-movement-tags.md`。本文件为改写与整合。

---

## 0. ★ 先分清两类标签（口径打架的根源）

| | **段落标签** | **enriched cue（增强提示）** |
|---|---|---|
| 例 | `[Verse 1]` `[Chorus]` `[Bridge]` `[Outro]` | `[Bridge - Quiet Contrast]` `[Final Chorus - Final Surge, Ad-Lib Finale]` |
| 数量 | **每段一个，必须有** | **整首 4–8 个，每段 1–2 个** |
| 作用 | 告诉后端这是什么段 | 告诉后端这一段怎么演 |

> ⚠️ **旧口径「每段最多 5–8 个标签」应理解为「整首的标签总预算」**——
> 若真按每段 5–8 个塞，一首 8 段的歌会挂上 40–60 个标签，后端会开始忽略它们。
> **正确预算是：段落标签若干 + enriched cue 4–8 个。**

---

## 1. ★★ 节制规则

1. **完整歌曲约用 4–8 个 enriched cue**（不是每段都用）
2. **用 enriched cue 时，每段 1–2 个**
3. **别给每一种人声质感都打标签**——**全局人声方向交给 Style 框**，不要在歌词里逐句标
4. **优先打在这几个结构要点上**：
   `intro` · `pre-chorus 的抬升` · `第一次副歌的爆发` · `bridge / breakdown 的对比` ·
   `末次副歌` · `outro`
5. ★ **如果生成器忽略了你的标签，是简化它们，不是加更多**
6. **不用生僻或自造标签**，除非用户明确要实验

### 怎么嵌（硬格式）

> **所有律动、表演、配器、增强提示，都必须嵌在段落标签内部**——
> 写成 `[Bridge - Quiet Contrast]`、`[Final Chorus - Final Surge, Ad-Lib Finale]`，
> **不要作为独立标签另起一行，也不要内联在歌词句子中间。**

理由：独立成行的 `[spoken]` `[whispered]` `[ad-libs]` `[call and response]`
会被后端当成**额外的一段**或**一句要唱的词**处理（对应 `SKILL.md`「交付格式六条」第 3、4 条）。

---

## 2. 中文标签表（基础，与 `SKILL.md` 一致）

| 类别 | 标签 |
|---|---|
| 结构 | `[Intro]` `[Verse]` `[Pre-Chorus]` `[Chorus]` `[Post-Chorus]` `[Bridge]` `[Instrumental Break]` `[Outro]` `[Silence]` |
| 演唱 | `[Whispered]` `[Belted]` `[Falsetto]` `[Harmonies]` `[Choir]` `[Spoken Word]` `[Raspy]` `[Breathy]` |
| 能量 | `[Low Energy]` `[Building Energy]` `[Explosive]` `[Emotional Climax]` `[Gradual Swell]` |
| 氛围 | `[Melancholic]` `[Nostalgic]` `[Intimate]` `[Dark Atmosphere]` `[Euphoric]` |
| 音效 | `[Vinyl Crackle]` `[Rain]` `[Applause]` `[Static]` |

**不要自相矛盾**（同段别同时写 `[Calm]` 和 `[Aggressive]`）。
**风格描述里不写艺人名**——写风格特征（`周杰伦风格` → `中式旋律说唱，钢琴与弦乐主导，含蓄内敛的男声`）。

---

## 3. 标签族索引（英文 enriched cue，按需取用）

| 族 | 内容 | 什么时候用 |
|---|---|---|
| **结构段** | intro / motif / verse / pre-chorus / chorus / hook / bridge / interlude / instrumental / outro / ending | 所有歌 |
| **律动与能量** | `slow build` · `rising tension` · `release` · `final surge` · `pulse shifts` · `rubato` · `locked groove` · `accelerando` · `ritardando` | 要调配器运动感时 |
| **质感与配器** | `drone beds` · `pedal tones` · `sparse percussion` · `full rhythm section` · `call and response` · `harmony layers` · `interlocking patterns` · `filters` · `noise` · `glitch` | 要精细控制编制层次时 |
| **人声表现** | `spoken intro` · `chanted hook` · `melismatic lifts` · `group responses` · `lead improvisation` · `harmony stacks` | 人声是主角时 |
| **形式发展** | `theme return` · `variation` · `expansion` · `compression` · `hard cut` · `fake ending` · `climax` · `cadence` · `subject/answer entries` | 要控制曲式走向时 |
| **曲风形式** | EDM / pop / rock / metal / rap / Latin / Afro-diasporic / South Asian / East Asian / gamelan / jazz / roots / minimalist 各自的惯用标签 | 写特定曲风时 |
| **混合律动** | `acoustic-to-electronic drop` · `orchestral/trap hybrid` 一类 | 做跨风格融合时 |

**路由**：普通歌词 → 结构段（+ 可选人声表现）；要配器运动 → 律动能量 + 质感配器；
特定曲风 → 曲风形式；实验融合 → 混合律动。

---

## 4. 与交付格式的关系（重要）

**默认交付的 `.txt` 是纯段落标签版**——里面**只应有 `[段落名]` 和歌词行本身**。

所以本文件的作用是：**当用户要"带标签的增强版"时，按这套规则加**；
**不要往默认交付物里塞 enriched cue**（对应 `SKILL.md`「交付格式六条」第 3 条：
词里任何注释都会被唱出来）。

**要给增强版时**，正确形态：

```text
[Intro - Sparse Motif]

[Verse 1]

[Chorus - First Payoff, Harmony Stack]

[Bridge - Quiet Contrast]

[Final Chorus - Final Surge, Ad-Lib Finale]

[Outro - Afterglow]
```

（整首 enriched cue = 6 个，落在 §1 第 4 条点名的结构要点上。）
