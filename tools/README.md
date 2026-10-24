# 翻译质检工具

译者自用的审计脚本。**它们依赖从游戏里提取的原始数据，克隆本仓库后无法直接运行**——
`extracted/` 里放的是游戏文案与反编译产物，受版权限制不随仓库分发。这些脚本留在仓库里，
是为了让整套质检过程可复现、结论可验证，而不是提供一个开箱即用的工具。

## 运行前提

- 需要自己从游戏目录提取出 `extracted/`，至少包含：
  - `zh_CN.po` —— 当前译本的**工作快照**
  - `context.json` —— 每条文案的归属（`po_context.py` 生成）
  - `all_keys.txt` —— 全部 key 清单（`check_po.py` 对账用）
- 全部**从游戏根目录运行**：脚本里 `extracted/...`、`Melvor2.exe` 都是相对路径
- 正式译本是仓库里的 `mod/zh_CN.po`；`extracted/zh_CN.po` 是它的快照，改完要同步回去

## 为什么必须这么查

PO 用英文原文当 msgid、没有 `msgctxt`，所以「一个英文串 = 一种译法」。像 `String` 既可能
是绳子也可能是弓弦，`Log` 既可能是原木也可能是日志——**这类错必须靠"这一条属于哪个对象"
才能判断**，而对象信息只存在于游戏数据包里。

## 脚本清单

| 脚本 | 作用 |
|---|---|
| `po_context.py` | 查一个词在数据包里的归属（Id / Category / Subcategory），产出 `extracted/context.json` |
| `po_audit.py` | 全量体检，产出 `extracted/audit/report.md` 与 5 个 tsv |
| `style_audit.py` | 二轮体检：人称、标点、BBCode 完整性、换行数、标签长度、中英混排空格 |
| `name_tail.py` | 尾词 ↔ 中心字核对（`Ore`→矿、`Boots`→靴），找分类错或漏中心词的名字 |
| `dup_target.py` | 找「不同英文译成同一中文」的组 |
| `derived_check.py` | 派生词词根核对：种子↔植物、原木↔树、掉落物↔怪物、单复数 |
| `homophone.py` | 中文连读同音检测（「瘟疫翼」这类拗口名） |
| `term_report.py` | 列出某个英文词的全部译法 |
| `term_split.py` | 用中文 n-gram 反推每种译法各占多少条，定出多数派 |
| `gen_fixes_v2.py` / `gen_fixes_v3.py` | 把裁决（`scope / 旧词 / 新词`）展开成逐条精确的 `fixes_*.tsv` |
| `apply_fixes.py` | 按 tsv 批量改写 `msgstr`，可选同步到游戏目录 |
| `append_po_entries.py` | 补「根本没进 PO」的串 |
| `tidy_colon.py` | 收掉全角冒号后面残留的半角空格 |
| `check_po.py` | 结构终检：条目数、重复 msgid、畸形行、占位符一致性 |

`fixes/fixes_vN.tsv` 是历次裁决的记录，共 48 批，按批次顺序套用即可复现当前译文。

## 1. 看上下文：po_context.py

```bash
python tools/po_context.py --probe String --probe Logs
```

输出该词在数据包里的归属。`String` 那条能看到它的配方是 `Flax → String`，同子类目下
另一条配方产出 `Bowstring`，所以 `String` 是绳子，不是弓弦。

## 2. 全量体检：po_audit.py

```bash
python tools/po_audit.py
```

产出 `extracted/audit/report.md` 和 5 个 tsv：

| 文件 | 内容 |
|---|---|
| `p0_untranslated.tsv` | 译文为空（210 条，全是数字 / 单位 / 引擎类型名，刻意不译） |
| `p1_leftover_english.tsv` | 中文里还夹着英文词（已过滤罗马数字 / 品牌 / 占位槽） |
| `p2_term_drift.tsv` | 含某词的短标签没用该词的既定译法 ← **主要工作清单** |
| `p3_overloaded.tsv` | 同一中文对应多个不同英文 |
| `p4_near_duplicate.tsv` | 大小写 / 单复数条目译法不一（多数是 `+` / `:` 这类符号差异，噪声） |

脚本会先剥掉 BBCode（`[img height=1.25em]`、`[effectIcon/]`）、`{占位符}`、`res://` 路径
再判断，不然误报会多出好几百条。P1 还额外放行三类「本来就该留英文」的东西：罗马数字
（`Crafting Station III`）、品牌与协议词（Patreon / Steam / base64）、运行时槽位
（`[Companion Name]`、`<qty>`）。没有这层白名单，P1 几乎全是假阳性。

## 3. 查一个词的所有译法：term_report.py

```bash
python tools/term_report.py --term Wizard --term Rod --max-words 3
python tools/term_report.py --auto 60 --out extracted/audit/terms.md
```

一眼能看出某个词被翻成了几种中文（`Meteorite Rod` 曾经是「法棒」，其余全是「鱼竿」）。

## 4. 数清楚分裂程度：term_split.py

`term_report.py` 只能列条目，看不出「到底哪一边是多数」。这个脚本用中文 n-gram 反推：

```bash
python tools/term_split.py --term Wizard --term Leather
```

```
=== Wizard  (122 条)  巫师 82/±0  |  法师 40/±10
```

意思是含 `Wizard` 的短标签里，82 条用「巫师」、40 条用「法师」。**多数派就是该统一的写法**。

> ⚠️ `po_audit.py` 的「期望译法」是从**单词条目**反推的，而单词条目自己经常是异类
> （`Wizard` 单条 = 法师，但 82 条组合名都是巫师）。所以定裁决前必须用 term_split
> 再看一眼多数派，别照着 P2 的 hint 直接改，否则会把正确的一大批改错。

## 5. 改：术语表 + 逐条修正

`tools/glossary.tsv`：裁决过的术语写这里（`英文<TAB>标准中文<TAB>备注`），`po_audit.py`
会自动加载同目录的这份表并优先采用，以后新翻译也照它来。**改术语只需要改这一张表 +
跑一次修正**。

中文组词时会省略尾字（靴子→靴、骨头→骨、箭头→箭），所以一个词往往有 2–3 个**都正确**的
写法。标准中文一栏支持用 `|` 列出可接受写法，只要命中任一个就不再报错：

```
Boots	靴子|靴	单件用靴子，组合名用靴
Spirit	灵魂|精灵	Spirit Box 用灵魂，风/火/土 Spirit 是元素精灵
```

这一步是让 P2 从「上千条噪音」变成「几百条真问题」的关键——**没有变体机制，体检报告
就没法当工作清单用**。

`fixes/fixes_vN.tsv` 两种写法：

```
String	绳子                         # 2 列：精确指定 msgid 的新译文
Fishing Rod	钓竿	鱼竿              # 3 列：msgid 含"Fishing Rod"的条目里，把「钓竿」换成「鱼竿」
```

```bash
python tools/apply_fixes.py tools/fixes/fixes_v1.tsv --dry-run
python tools/apply_fixes.py tools/fixes/fixes_v1.tsv ^
       --deploy-to "<游戏数据目录>"
```

按行只改 `msgstr`，不重排、不重生成，幂等；`--deploy-to` 会同步到游戏目录，**重启游戏后生效**。

改完记得跑一次结构校验（从游戏根目录运行）：

```bash
python tools/check_po.py        # 应输出 RESULT: ALL GREEN
```

## 6. 补「根本没进 PO」的串：覆盖核对

前面几轮查的都是「PO 里有这条、但译得不对」。还有一类是**压根没有 PO 条目**，
所以再怎么体检都查不到——游戏只能显示英文原文。

游戏里有若干数据字段会走翻译系统，但早期抽取只抓了 `DisplayName`：

| 字段 | 内容 | 当时缺失 |
|---|---|---|
| `Observation` | 星象学观测文案（整句） | 78 |
| `DialogueText` | 多段剧情对话 | 20 |
| `CompletedDescription` | 任务完成短句 | 20 |
| `UnlockText` | 「本次观测解锁…」 | 7 |
| `ResistanceName` | `Normal Resistance` | 1 |
| `DisplayNameShort` | GP / SC / PP / 伤害加成 | 4 |

核对办法（对着 `Melvor2.exe` 内嵌 JSON 取值，再和 PO 的 msgid 求差集）：
正则必须写成 `((?:[^"\\]|\\.){2,4000})`——早先的 `[^",}\\]` 会在**逗号处截断**，
于是长句全部「看起来已存在」，这就是这批缺口一直没被发现的原因。

补齐：

```bash
python tools/append_po_entries.py --dry-run
python tools/append_po_entries.py --deploy-to <游戏数据目录>
```

它同时把新 key 追加进 `extracted/all_keys.txt`（`check_po.py` 会拿这份清单对账），
所以补完仍然是 ALL GREEN。**换行在 PO 里写成 `\n` 两个字符**，gettext 解析时会还原成真换行，
正好等于游戏运行时查表用的 key。
