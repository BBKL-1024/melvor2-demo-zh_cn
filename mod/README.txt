Melvor Idle 2 试用版 简体中文补丁
==================================

本补丁不改动游戏的任何原有文件。它借助 Godot 引擎自带的 override.cfg 机制，
让游戏启动时自动加载一个翻译脚本。

安装后游戏根目录只会多出两样东西：一个 override.cfg，一个 mod 文件夹。


一、安装
--------

把这两个东西复制到游戏根目录，也就是 Melvor2.exe 所在的那一层：

    override.cfg
    mod\            （整个文件夹，连同里面的文件）

Steam 里找目录：库 → 右键 Melvor Idle 2 → 管理 → 浏览本地文件。

注意是 exe 所在目录，不是 data_GamesByMalcs.Melvor2_windows_x86_64 那个子目录。
放好之后游戏根目录大概长这样：

    Melvor2.exe
    override.cfg
    mod\
        zhpatch.gd
        zh_CN.po
        README.txt
    data_GamesByMalcs.Melvor2_windows_x86_64\
    ...

mod 文件夹必须和 override.cfg 放在同一层，不要拆开，也不要改名字。

不需要管理员权限。放好后从 Steam 正常启动，界面就是中文。


二、确认是否生效
----------------

界面是中文就算成功。

想进一步确认，看 mod 目录下有没有生成 zhpatch.log，第一行写着：

    Melvor2 ZhPatch (GDScript) starting

再往下找这一行，说明词表两个方向都验过了：

    self test: other direction ok | after restore ok -> switchable=true


三、切换语言
------------

游戏里：设置 → 界面设置（Interface Settings），第一行是「语言 / Language」
下拉框，选「简体中文」或「English」，选择会被记住。

按 Ctrl+T 可以临时切到另一种语言对照原文，这次切换不保存。

也可以直接改 mod 目录下的 language.cfg（游戏内切换后自动生成）：

    language=zh_CN     简体中文
    language=en_GB     English


四、卸载
--------

删掉 override.cfg 和 mod 文件夹即可。

mod 里的 zhpatch.log 和 language.cfg 是运行后生成的，一并删掉也行，
删不删都不影响。

删完之后游戏和从未装过补丁完全一样 —— 这个方案从头到尾没有修改过任何
游戏原有文件。


五、Steam 更新之后
------------------

不需要做任何事。override.cfg 和 mod 文件夹都是新增的，不在 Steam 的更新范围内，
游戏更新完还在，翻译照常生效。


六、出问题了
------------

先看 mod 目录下的 zhpatch.log，里面会写明卡在哪一步。常见几种：

  CATALOG MISSING
      zh_CN.po 不在 mod 文件夹里，或者被改名了。

  FONT: no CJK font file found
      系统里没找到中文字体（正常 Windows 都有 DengXian / 微软雅黑 / 黑体），
      这种情况中文会显示成方块。

  settings hook: switching unavailable, dropdown not installed
      语言自检没过，游戏内下拉框不会出现，翻译本身通常仍然是好的。

整段日志一行都没有，说明 override.cfg 没被读到，检查它是不是在 exe 同目录、
名字有没有写错。


文件说明
--------

override.cfg   必须放在游戏根目录。Godot 启动时从这个固定位置读取它，
               内容只有一句 autoload 声明：ZhPatch="*res://mod/zhpatch.gd"
mod\zhpatch.gd 补丁本体。启动时解析 po、注册翻译表、挂中文字体、
               在设置页插入语言下拉框
mod\zh_CN.po   翻译表（msgid 是游戏里的英文原文）
mod\README.txt 本文件
