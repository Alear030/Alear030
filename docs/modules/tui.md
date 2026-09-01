# Alear030 TUI

**中文** · English（暂缺）

← [返回 README](../../README.md) · [文档目录](../index.md)

`tui/` 是 Alear030 的终端界面，基于 [Textual](https://textual.textualize.io/) 8。它的职责边界很窄：**接收 `Loop` 的流式事件并渲染**，不参与编排、不持有业务状态。

本文讲机制。架构总览见 [架构文档](../ARCHITECTURE.md)，新增 widget 的写法见 [扩展指南](../EXTENDING.md)。

> **本文所有技术断言都对着代码核对过。** 没核实的推测一律不写，已知的粗糙处在最后一节如实列出。

---

## 目录

- [三层结构](#三层结构)
- [事件流](#事件流)
- [线程模型](#线程模型)
- [Widget 注册体系](#widget-注册体系)
- [事件分发注册表](#事件分发注册表)
- [Textual 的几个坑](#textual-的几个坑)
- [已知的粗糙处](#已知的粗糙处)

---

## 三层结构

| 层 | 文件 | 职责 |
|----|------|------|
| App | `tui/tui_core.py` | `Alear030TUI`：channel 路由、输入提交、worker 线程、全局绑定 |
| Channel | `tui/tui_channel/tui_channel_core.py` | `TuiChannel`：一个 agent 一条频道，持有滚动区与 widget 缓存 |
| Widget | `tui/tui_widget/` | 注册体系 + 各 widget 实现，一个 widget 一个目录 |

`Alear030TUI` 是入口 App。构造时 **把自己的 `receive_loop_emit` 挂到 `loop.emit` 上**——这是 TUI 与 Loop 之间唯一的接线：

```python
self.loop.emit = self.receive_loop_emit
```

`main.py` 装配时把 `loop` 传给 TUI，接线在 TUI 的 `__init__` 里完成。Loop 侧只知道有个 `self.emit` 可调，不知道渲染层长什么样。

## 事件流

```text
loop.emit(event, content, stream_id, agent_name)
  → Alear030TUI.receive_loop_emit
      → 底栏认领的 event 先截走（bottom_bar.event_methods 查表），不进 channel
      → 其余按 agent_name 找 TuiChannel
      → call_from_thread 送回 UI 线程
  → TuiChannel.handle_loop_emit → 查 event_methods 表分发
  → append_once / append_stream
  → tuiwidgets.build_widget(type, content) 构造并挂载
```

**事件名是语义化的，不感知渲染层**：`AssistantContent`、`AssistantThinking`、`AssistantThinkingStreamEnd`、`AssistantToolCallUpdate`、`StreamEnd`、`LoopStart`、`LoopEnd`、`SystemError`。

用户可见的 harness 错误走 `SystemError`；工具自身的错误走 `_error_result` / `tcr` 的 `extra_info`，**不另开通知总线**。

未知事件不静默丢弃——`handle_loop_emit` 会挂一条 `SystemError` widget 把事件名显示出来。

### 流式与一次性

- `append_once`：一次性内容，构造后挂进滚动区，存进 `once_widgets`
- `append_stream`：流式内容，按 `widget_id` 查 `stream_widgets`——**没有就建，有就调 `update_widget`**

所以每个流式 widget 必须实现 `update_widget`。累积在 Loop 侧完成，`update_widget` 拿到的是**整段替换**而不是增量拼接。

`StreamEnd` 按 `stream_id` 后缀归组，把该流下全部 widget `finalize()` 后从缓存移除——**同一条流可以挂多个 widget 类型**（比如一次回复既有 thinking 又有 content）。

## 线程模型

```text
Input.Submitted（UI 线程）
  → do_work（@work(thread=True) → worker 线程）
  → 一轮 loop 执行，边跑边 emit
  → receive_loop_emit 在 worker 线程被调用
  → call_from_thread 把 mount/update 送回 UI 线程
  → finally 解锁输入
```

**widget 的挂载与更新必须在 UI 线程。** `call_from_thread(func, *args)` 传的是**函数引用**——写成 `call_from_thread(func(x))` 就是在当前线程先执行完再把返回值传过去，等于没送回 UI 线程。

`receive_loop_emit` 里底栏事件有个例外分支：先比对 `threading.get_ident()`，已经在 UI 线程就直接调，不绕 `call_from_thread`。

worker 用 `@work(thread=True, exit_on_error=False)` 起，内部再包一层 `try`——双保险，防止 worker 异常直接杀掉整个 App。

## Widget 注册体系

一个 widget 一个目录，`@widget_register` 注册类，`tuiwidgets.build_widget(type, content)` 按类型构造。

```python
@widget_register(widget_type="AssistantContent", widget_css_file=..., widget_enable=True)
class AssistantContentWidget(...):
    def __init__(self, widget_content, widget_id=None): ...
    def update_widget(self, widget_content): ...
    def finalize(self): ...
```

自动发现：`tui/tui_widget/tui_widgets/__init__.py` 遍历自己目录下的一级子目录并 `import_module`，触发装饰器注册。**下划线开头的目录会被跳过**——这是禁用一个 widget 的办法之一。

注册时同时收集该 widget 的 `.tcss` 文件路径进 `css_files`；`tui_core.py` 在 import 期把它和全局 `tui_style.tcss` 拼成 `css_path` 传给 `App.__init__`。

**未注册或 `widget_enable=False` 的类型不会炸**，`build_widget` 用一个默认 `Static` 兜底渲染，把类型名显示出来。

## 事件分发注册表

`TuiChannel` 的事件分发用了一张模块级注册表：

```python
event_methods: dict[str,str] = {}          # event 名 → handler 方法名
def event_register(event: str): ...        # 装饰器
```

**注册表放模块级而不是类内是刻意的**：类体里跑装饰器时还没有实例，注册表放类里要和 `__init__` 的实例属性纠缠，语义容易踩坑。

底栏（`BottomBar`）有自己的一份同名机制 `event_methods`，`receive_loop_emit` 先查它——**底栏认领的事件不进 channel**。

## Textual 的几个坑

这几条都是踩出来的，违反了不会报错，只会渲染成别的样子：

- **自定义 `Widget` 不写 `height` 会默认填满父容器。** 消息类 / 条目类 widget 的 css 第一条必须写 `height: auto`。内置 `Static` / `Markdown` 的 `DEFAULT_CSS` 自带 `auto`，继承它们的不用写。
- **`App.__init__` 的 `css_path` 是关键字参数**——第 1 个位置参数是 `driver_class`，写成位置参数会静默传错。
- **`set_focus` 传 widget 对象，不传 CSS 选择器字符串。**
- **`tool_call_extra_info` 的 css 走 `ExtraInfoHandler._widget_css_handler`**：写 `margin-*` / `padding-*` 子属性会被聚合成 `margin` / `padding` 元组，因为 Textual 内联样式只认复合属性，`setattr` 对带连字符的属性名不生效。单词属性（`color` / `width` / `height`）直接生效。
- **贴底靠 Textual 原生 `anchor(True)`**，不自己维护跟随态。显式贴底只在「用户提交新一轮」时调一次——跟随中的自动贴底由 compositor 每次 `arrange` 负责。这一次调用是为了处理「用户上滚看过历史」的情况：那时 `_anchor_released=True`，compositor 停止跟底，靠 `anchor()` 内部的 `scroll_end` 把它清掉才能恢复跟随。

## 已知的粗糙处

- **channel 表当前只登记 `main`。** `TuiChannel` 按 `agent_name` 路由的结构已经铺好，运行时临时构造的 subagent 也已写入 agents 容器供按名路由，但 `_channel_init()` 目前只建一条 main channel——subagent 的输出没有独立频道。
- `tui_core.py` 里输入锁有一条 `@claude` 备注：中途打断能力做出来之后，这套 lock 要重看。
- **DOM 窗口化已于 20260825 回退**，完整实现存档在本地分支 `tui-channel-window`。回退不是因为没跑通，是代价错位——重建要求 channel 侧长期维护一份与 widget 平行的 `restore_content`，每新增一种流式 widget 都要回 channel 补一条合并规则，widget 注册体系「加 widget 只碰自己目录」的局部性被打破。当时踩出来的五条坑记在 `tui_channel_core.py` 顶部注释里，下次真要做直接看那里。
