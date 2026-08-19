---
name: scan-claude-markers
description: "扫描 Alear030 仓库里用户留在代码注释中的 @claude / @claudecode 任务标记，列出待办并可选地逐个执行。当用户说'扫一下我的 @claude 标记'、'看看有哪些待办'、'我在代码里留了任务给你'、'处理一下 @claude'、'checkclaude marker'之类时使用。SessionStart hook 只在会话开始扫一次，这个 skill 让用户能在对话中任意时刻重新扫描（比如刚埋完新标记、或做完一批想复查还剩哪些），所以只要用户想主动触发一次标记扫描就用它，别自己 grep。"
---

# 扫描 @claude 代码任务标记

用户习惯把任务埋在代码现场——在注释里写 `# @claude <要做的事>`，而不是切回对话框描述"哪个文件哪一行要改啥"。标记就在上下文里，比口头描述精准。这个 skill 做的就是把散落全仓库的这些标记捞出来、列给用户看，必要时逐个执行。

会话开始时有 SessionStart hook 自动扫一遍，但用户经常在会话中途埋新标记、或做完一批想复查剩余，这时就需要主动重扫——这就是这个 skill 存在的理由。

## 三种标记语义（扫描时必须区分）

| 写法 | 含义 | 扫描处理 |
|------|------|---------|
| `# @claude <事>` | 待办任务，给我的 | **列出来** |
| `# done(@claude): <做了啥>` | 已完成的痕迹 | **排除**（做完后由待办改写而来，保留是为了留档，不该再当待办报） |
| `# @claude(ignore) <备注>` | 用户给自己的笔记，不是给我的 | **排除**，而且我也别去动那行代码 |

## 扫描命令

在仓库根目录跑这条（Git Bash）。它匹配 `@claude`/`@claudecode`，再用第二层 grep 滤掉 `done(@claude)` 和 `@claude(ignore)`：

```bash
cd "D:/Alear030" && grep -rniE "@claude(code)?\b" \
  --include="*.py" --include="*.md" --include="*.yaml" --include="*.yml" --include="*.txt" \
  --exclude="CLAUDE.md" \
  --exclude-dir=".git" --exclude-dir=".claude" --exclude-dir="session_detail" --exclude-dir="session_plan" \
  --exclude-dir="local_model" --exclude-dir="workspace" --exclude-dir="z_ccstudy" --exclude-dir="z_old_code" \
  . 2>/dev/null | grep -viE "done\(@claude|@claude\(ignore" || echo "没有待处理的 @claude 标记"
```

- **只扫源码/文本**（py/md/yaml/yml/txt），排除 `session_detail`/`session_plan`/`local_model` 等数据目录——那些会话 JSON 里一旦出现 @claude 就会成堆误报。
- **排除 `CLAUDE.md` 和 `.claude/` 目录**：这套 @claude 约定本身写在 CLAUDE.md 协作方式节和本 skill 里，扫到它们是在描述约定、不是真待办，会误报。
- 无匹配时输出"没有待处理的 @claude 标记"，直接如实告诉用户仓库干净，别硬编。

## 列给用户看

扫完把结果整理成清单，每条带 `文件:行号` 和标记内容，方便用户点击跳转。别只贴 grep 原始输出——按文件分组、把每条的任务描述拎清楚。如果标记本身语焉不详（比如只写 `# @claude 检查`），如实指出这条不清楚、需要用户澄清要检查什么，别自己脑补。

## 做完之后：改写成 done 痕迹，不要删

用户明确要求过：任务做完后，把那行 `# @claude <事>` **改写成 `# done(@claude): <做了什么>`**，而不是删掉整行。

- 保留痕迹让用户一眼看到我干过什么，也让下次扫描自动排除它（第二层 grep 会滤掉 `done(@claude)`）。
- 用 file_edit 类工具精确替换那一行，别动周围代码。
- 如果一次做了多个标记，逐行改写，别漏。

## 边界

- 这个 skill 只负责**扫描 + 列出**，以及做完后的**改写**。要不要动手做某个标记的任务，听用户的——用户可能只是想看看还剩哪些，不一定让你全做。列出来后问一句"要我现在处理哪些"，别默认全扫全做。
- 别去碰 `@claude(ignore)` 那些行，那是用户的私人笔记。
