# lyric-writing

**四模式中文/粤语/英文歌词创作与诊断 skill** —— 面向 AI 音乐生成（Suno 等）的作词工作台。

遵循 [Agent Skills](https://agentskills.io) 开放标准，Claude Code / Codex / OpenCode /
Hermes Agent / OpenClaw / Cursor 等客户端通用。

---

## 它解决什么问题

用 AI 写歌词，最容易得到的是一段"语法正确、押韵工整、意象丰富，
**而这四段可以属于任何一首歌**"的文字。

这个 skill 收录的是一套**可判定的作词判据**——不是"多写几版"，
而是每一条都能回答"这样写对不对、为什么"：

| 能力 | 说明 |
|---|---|
| **落音元音设计** | 把元音按**动作**分类（`/oʊ/` 滑下去＝下沉、`/ɑr/` r 化挂住＝悬停、`/eɪ/` 亮、`/aɪ/` 压），用来设计副歌的**低音落点**；含"低音配额"（低频是配额，不是弥漫气氛）与"换意境必须重跑落音审计" |
| **倒字检测** | 普通话**字调 × 旋律走向**的冲突检测——"深爱"唱成"神爱"这类**语义跑偏**。含赵元任五度标调表、风险计分公式、三类高发位置、**从严三条 / 从宽五条**、五种改法 |
| **韵的两套体系** | 普通话十三辙 ＋ 粤语韵部（九声六调、入声禁忌、协音规则），**互不通融**；另有"韵的稳定性层级"与"窄辙反而出好词" |
| **段长上限与时长换算** | 12 个曲风族的段长硬上限（Suno 段落过长会抢拍、压缩、**丢行**）、目标时长↔词数表、BPM 感知行数 |
| **AI 味终检** | 十二条可枚举症状 ＋ 英文套话清单 ＋「十二条全过了还是像 AI」的四个征兆 |
| **意象系统化** | 七种感官分布、同调词生成法、重力法则（先展示后告知）——判据是"这些意象能不能出现在同一个场景里" |
| **Suno 交付格式** | 六条硬约束（段内换行＝换气点、括号＝伴唱、**注释会被唱出来**…）＋ V6 字段与滑块（Exclude Styles、商业录音室修正、Style Influence） |
| **13 项交付自检** | 每次交付必附的检查表 |

---

## 四个模式

| 模式 | 什么时候触发 | 产出 |
|---|---|---|
| **A · 器乐已定** | 用户给了风格提示词 + 已跑好的器乐，只缺歌词 | 直接填词，**细节不问** |
| **B · 只有想法** | 只有一个主题 / 意境 / 参照歌手 | 多套方案 + 直接写完推荐方案 |
| **C · 诊断现有歌词** | 用户贴来现成歌词问"怎么样" | 十二行拆解表 + P0/P1/P2 问题清单 + **不要动的亮点**，不整篇重写 |
| **D · 词稿改写** | 跨语言改写（普→粤）或优化缩短 | 改好的成品 + 逐行改动清单 |

**核心原则：缺关键信息就一次问清。** 只问决定性的变量（语言 / 主题 / 参照对象），
细节自己定；一次问完，不逐个挤牙膏。能推断的自己推断，并在自检里标明哪几项是推断的。

---

## 安装

```bash
# 方式一：一条命令（skills.sh）
npx skills add bq1998-dot/lyric-writing

# 方式二：手动 —— 把 lyric-writing/ 整个目录复制到对应位置
~/.claude/skills/          # Claude Code
~/.agents/skills/          # Codex（推荐真身放这里，其余目录做软链）
~/.config/opencode/skills/ # OpenCode
~/.hermes/skills/          # Hermes Agent
~/.openclaw/skills/        # OpenClaw
```

**推荐姿势**：真身放 `~/.agents/skills/lyric-writing/`，
其余各客户端的 skills 目录里放**软链接**指过去——一份真身，五家通吃。

---

## 文件结构

```
lyric-writing/
├── SKILL.md                      正文：四模式 + 写词规则 + 13 项自检 + Suno 交付
└── references/                   按需加载，不要一次全读
    ├── rhyme-zh.md               普通话十三辙 + 选韵决策表 + 用韵禁忌
    ├── rhyme-yue.md              粤语韵部 + 九声六调 + 入声禁忌 + 协音
    ├── tone-check.md         ★   倒字检测（字调×旋律）+ 句尾平仄 + 从宽从严
    ├── english-advanced.md   ★   英文 Hook 落音设计 + 低音配额 + 元音动作表
    ├── section-limits.md     ★   段长上限（12 曲风族）+ 时长↔词数 + BPM 感知行数
    ├── ai-tell.md            ★   十二条 AI 味症状 + 套话清单 + 终检清单
    ├── pronunciation.md      ★   同形异音词表 + 生造缩写禁令 + 三种重拼手段
    ├── imagery-system.md     ★   七感 + 同调词 + 重力法则 + 意象自检
    ├── case-dissect.md       ★   十二行拆解表 + 改稿方向
    ├── tag-guide.md          ★   标签节制（整首 4–8 个）+ 标签族索引
    └── suno-v6.md            ★   V6 字段上限 + 四条行为 + 五项固定动作
```

正文已含每次必用的判据；`references/` 是"需要时再翻"。
**单次任务通常只需正文 + 1–2 个 references。**

---

## 致谢

本 skill 的方法体系在多轮开源吸收中成形，以下三个项目的内容被研究、
比对并**改写重述**进了相关文件（无逐字转载）：

| 项目 | 协议 | 吸收了 |
|---|---|---|
| [jtydhr88/lyric-writing-skills](https://github.com/jtydhr88/lyric-writing-skills) | MIT | **倒字检测器**（五度标调、风险计分、三类位置、从宽从严）、普通话句尾平仄、意象系统化与同调词法、十二行拆解表、韵的稳定性层级、AI 味八条。★ 其 `NOTICE` 声明 MIT 不覆盖该库引用的工艺书原文，故本仓库**仅重述规则、未转载原文** |
| [bitwize-music-studio/claude-ai-music-skills](https://github.com/bitwize-music-studio/claude-ai-music-skills) | CC0-1.0 | **按曲风的段长上限表**、时长↔词数换算、BPM 感知行数、同形异音词表与生造缩写禁令、AI 味 Class 1–7、verse→chorus 回声检查 |
| [NuNaught/suno-songwriting-skill](https://github.com/NuNaught/suno-songwriting-skill) | Apache-2.0 | **references 渐进式披露的组织手法**、标签节制规则与标签族索引、可唱性翻译优先级 |

声律部分的上游依据可追溯至赵元任（五度标调）、王力《汉语诗律学》、
Pat Pattison《Writing Better Lyrics》等公开出版物的通行结论。

---

## License

MIT —— 见 [LICENSE](LICENSE)。
