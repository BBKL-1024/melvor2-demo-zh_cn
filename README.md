# Melvor Idle 2 试用版 简体中文补丁

为 [Melvor Idle 2 试用版](https://store.steampowered.com/app/3218350/Melvor_Idle_2/) 提供简体中文界面。安装后游戏目录只多出一个 `override.cfg` 和一个 `mod/` 文件夹，游戏的任何原有文件都不改动。

**[⬇ 下载最新版本](https://github.com/BBKL-1024/melvor2-demo-zh_cn/releases/latest)** — 解压到游戏根目录即可

## 做了什么

- 汉化约 8180 条文本，覆盖技能、物品、怪物、战斗、剧情、设置与全部界面
- 暂停菜单 → 设置 → 界面设置里新增「语言 / Language」下拉框，中英即时互切，选择记在 `mod/language.cfg`
- 中文字体从系统字体（DengXian / 微软雅黑 / 黑体）挂到主题 fallback 链，不出方块字
- 中文排版修正：原版只在空格处断行，中文会被撑出面板，补丁把断行模式改成 `WordSmart` 并放开任务页的自动高度
- 启动自检：词表是否挂上、两个方向的切换是否都成立，结果写进 `mod/zhpatch.log`

## 安装

下载 Release 里的 `Melvor2Zh-zh-CN.zip`，解压到游戏根目录——`Melvor2.exe` 所在的那一层，不是 `data_GamesByMalcs.Melvor2_windows_x86_64` 子目录。

解压后的结构就是最终结构：

```
Melvor Idle 2 Demo/
├─ Melvor2.exe
├─ override.cfg          ← 必须在根目录，Godot 从固定位置读它
├─ mod/
│  ├─ zhpatch.gd
│  ├─ zh_CN.po
│  └─ README.txt
└─ data_GamesByMalcs.Melvor2_windows_x86_64/
```

`override.cfg` 和 `mod/` 必须放在同一层，`mod` 不要改名或拆开。

Steam 里找目录：库 → 右键 Melvor Idle 2 → 管理 → 浏览本地文件。

放好后从 Steam 正常启动，界面就是中文。

## 卸载

删掉 `override.cfg` 和 `mod/` 文件夹即可，游戏回到原始状态。

`mod/zhpatch.log`、`mod/language.cfg` 是运行后生成的，删不删都不影响。

## 切换语言

暂停菜单 → 设置 → 界面设置 → 第一行「语言 / Language」。

也可以直接改 `mod/language.cfg`：

```
language=zh_CN     简体中文
language=en_GB     English
```

游戏内按 `Ctrl+T` 可以临时切到另一种语言对照原文。

## 翻译进度

| 项目   | 数量          |
| ---- | ----------- |
| 文本条目 | 8180        |
| 已翻译  | 7970（97.4%） |
| 未翻译  | 210         |

未翻译的 210 条是占位符、调试输出、存档字段名之类的内部技术串，翻译反而有害。术语表在 [`tools/glossary.tsv`](tools/glossary.tsv)，按代码里的实际语义定名。

## 实现原理

Godot 引擎在启动时会读取 `exe 同目录/override.cfg`，用它覆盖项目设置。补丁借这个官方机制声明一个 autoload：

```ini
[autoload]

ZhPatch="*res://mod/zhpatch.gd"
```

于是游戏启动时自动执行 `mod/zhpatch.gd`，由它完成四件事：

1. 解析 `mod/zh_CN.po`，把「英文原文 → 中文」注册进 `TranslationServer`（游戏自身也是用 gettext，英文原文就是 key）
2. 把系统中文字体挂到默认主题和项目主题的 fallback 链
3. 自检两个方向的翻译都能取到，通过后才放出语言下拉框
4. 监听节点变化，在设置页插入语言行，并给文本控件补上中文断行模式

切语言 = 把中文词表挂上或摘下，再广播一次翻译变更通知，界面下一帧自动重刷。

## 目录结构

```
mod/          补丁本体，解压后整个文件夹进游戏目录
├─ zhpatch.gd       补丁脚本
├─ zh_CN.po         翻译表
└─ README.txt       安装说明
override.cfg  必须放在游戏根目录（与 mod/ 同级），Godot 从固定位置读它
tools/        翻译质检脚本、术语表、批量修正表
build.ps1     把 mod/ 组装成 dist/Melvor2Zh-zh-CN.zip
```

`mod/` 是唯一来源：里面放什么，压缩包里就有什么。`build.ps1` 负责把 `override.cfg` 提到压缩包根目录、其余文件放进压缩包里的 `mod/`。

## 从源码构建

```powershell
.\build.ps1
```

产物是 `dist/Melvor2Zh-zh-CN.zip`：

```
override.cfg
mod/zhpatch.gd
mod/zh_CN.po
mod/README.txt
```

## 关于开发

补丁的代码与译文由 **DeepSeek-V4.1-Flash** 辅助完成，❤️🐳

它在这份仓库里做的事：

- 逆向游戏的语言加载链路，实测出 `override.cfg` + autoload 这条零侵入路径——包括 `res://` 能否加载子目录、会不会挤掉游戏自带的 3 个 autoload、切换后能否回落
- 编写 `mod/zhpatch.gd`，并在原版 dll 上反复实跑，靠自检日志和截图逐项核对，而不是只凭推测
- 8180 条文本的初译与术语定名，`tools/fixes/` 里 48 份批量修正表的整理
- `tools/` 下的质检脚本，以及 `build.ps1` 的打包与编码处理（PowerShell 5.1 那个 BOM 坑就是它踩的）

译文和代码都经人工审核、实机验证后才发布，功能取舍与验收由作者负责。

## 许可

- 代码（`mod/`、`tools/`、脚本）：[MIT](LICENSE)
- 翻译文本（`mod/zh_CN.po`、术语表）：[CC BY-NC-SA 4.0](LICENSE-TRANSLATION)

`zh_CN.po` 中 `msgid` 的英文原文版权归 Games by Malcs 所有，此处仅作翻译对照。
