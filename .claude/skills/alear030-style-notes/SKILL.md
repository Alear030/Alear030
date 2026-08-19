---
name: alear030-style-notes
description: 给 Alear030 用户的代码写/补注释、或往用户代码文件里落笔时使用。注释风格：中文、极简、动词/动作导向；禁止空标签注释；改用户代码时保留其标识符、同文件 helper 优先、先教后改。触发：用户要求加注释/写注释、即将往用户代码插入注释、或用户在自己写代码时需要讲解/同步改动。
---

# Alear030 注释风格（写进用户代码时）

给**用户的代码**加注释、或在用户代码文件里写/改时，贴合这套口味，不要用 Claude 默认的文档化风格。

写法纪律细节见项目 `.cursor/rules/coding-conventions.mdc`——本 skill 不复述全文。

## 核心原则

1. **中文，极简，动词/动作导向** — 说「这一块在干嘛 / 这个对象承载什么」，一句话甚至几个词。
2. **目的/意图优先，不写参数类型清单** — 不写 `param: dict | None`；契约用大白话（「构造的时候 widget cls 自取」）。
3. **保留英文标识符原文，不翻译** — `widget`、`Static`、`stream_id` 原样保留，中文包裹。
4. **用 `#` 行注释，不用 docstring**。
5. **冒号/逗号分隔的短句** — 「动作或对象 + 补充说明」，如 `# 注册widget到widget_list`。
6. **禁止空注释 / 装饰性标签** — 不要 `# 题干`、`# 选项` 这种只贴标签、不解释意图的注释。
7. **该注的地方说清楚为何存在** — index/id 干什么、这个 for 在扫什么、某个 node/widget 在结构里扮演什么——一句话讲「在干嘛」，别文档化罗列。

## 正例

```python
# 初始化创建，负载上widget list
def __init__(self):
    self.widget_list: dict = {}

# 防呆设计，阻止坏数据导致整个widget注册环节崩掉
if not widget_type:
    raise ValueError('widget_register failled')

# 注册widget到widget_list
self.widget_list[widget_type] = {...}

# 用 option index 当 id，回传时按 id 对齐答案
option_id = f'q{q_idx}_o{o_idx}'

# 扫 options，挂成可点的子节点
for o_idx, option in enumerate(options):
    ...
```

## 反例

```python
# ❌ 签名式参数说明 + 类型罗列
# 按 widget_type 查注册表构造一个 widget 实例返回
# widget_content: 内容 dict，最小约定 {'content': str, 'meta': dict|None}

# ❌ 空标签，没说意图
# 题干
# 选项

# ❌ 文档化罗列，不像在干嘛
# 遍历所有选项并创建 OptionWidget 实例挂到容器
```

## 改用户代码时（短纪律）

仍属「往用户文件里落笔」，不是整份 coding-conventions 重写：

1. **保留用户已有标识符** — 如 `question_option_item_*`，禁止擅自重命名「更规范」。
2. **同文件 `_helper` 优先** — 禁止为拆而拆新文件 / 平行模块 / 一堆微 helper。
3. **先教后改** — 用户在自己写时以讲解为主；只有用户明确说「接进去 / 同步 / 改」才落盘改代码。

## 应用时怎么落地

- 若用户已写了注释，先看那句的口味，**用同样的句长和结构**补其余，不另起一套。
- 只补「读代码时容易疑惑的地方」（空分支为何存在、兜底、公开入口、index/结构角色），不为每一行配注释。
- 拿不准时写出候选让用户拍板，别硬贴。
- 用户说「按我的风格注释」时，直接套本 skill 正例形态。
