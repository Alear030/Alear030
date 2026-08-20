# Alear030 扩展指南

**中文** · [English](EXTENDING.en.md)

← [返回 README](../README.md)

怎么给 Alear030 加一个工具、一个 Hook、一个 Prompt 分块或一个技能。每一节都是「照抄就能跑」的最小骨架 + 一段容易踩的坑。

架构背景见 [架构文档](ARCHITECTURE.md)，配置项见 [配置说明](CONFIGURATION.md)。

---

## 目录

- [先理解自动发现的三种深度](#先理解自动发现的三种深度)
- [加一个工具](#加一个工具)
- [加一个 Hook](#加一个-hook)
- [加一个 Prompt 分块](#加一个-prompt-分块)
- [加一个技能](#加一个技能)
- [验证你的改动](#验证你的改动)

---

## 先理解自动发现的三种深度

Hook、Prompt、Tool 都靠「import 执行装饰器注册」这个副作用工作，但**扫描深度不一样**，这是最常见的踩坑点：

| 系统 | 扫描什么 | 意味着 |
|---|---|---|
| Hook | 递归 `hook/hooks/**/hook.py` | 放多深都能被找到，但文件名必须叫 `hook.py` |
| Prompt | 只扫 `prompt/prompts/` 的**一级目录**，加载固定的 `prompt.py` | 不支持嵌套，`prompt/prompts/a/b/prompt.py` 不会被发现 |
| Tool | 只导入 `tool/tools/` 下的**一级 package** | 嵌套的 `tool.py` 不会仅因文件存在就注册，package 的 `__init__.py` 必须显式 import |

三者都会跳过以下划线开头的目录（`_experiment/`、`__pycache__/`），需要临时禁用某个模块时可以直接给目录名加下划线前缀。

---

## 加一个工具

### 目录骨架

```text
tool/tools/my_tool/
├── __init__.py        # 必须显式 import,否则不会被注册
├── tool.py            # 实现
└── tool_prompt.md     # 可选:这个工具的详细使用说明
```

`__init__.py`：

```python
from .tool import my_tool
```

> **这一行是整个流程里最容易漏的。** `tool/__init__.py` 只 import `tool/tools/` 下的一级 package，package 内部有没有把实现暴露出来它不管。漏了这行，工具静默不注册，模型侧看不到任何报错。

### 实现

```python
from pathlib import Path

from tool.tool_core import register_tool, tool_call_processing

tool_desc = '一句话描述这个工具做什么，会进 tool_prompt 的工具清单'

# 有 tool_prompt.md 就读进来，没有就传 None。这段是各工具通用的模板写法
tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
if tool_prompt_file.exists():
    content = tool_prompt_file.read_text(encoding='utf-8').strip()
    tool_prompt = content if content else None
else:
    tool_prompt = None


@register_tool(
    tool_name='my_tool',
    tool_desc=tool_desc,
    tool_prompt=tool_prompt,
    tool_enabled=True,
    tool_autho='basic_tool',
)
def my_tool(query: str, limit: int = 10, **kwargs) -> str:
    # 统一的调用记账,几乎所有工具第一行都是它
    tool_call_processing(kwargs.get('tcr', None), kwargs.get('emit', None))

    # 参数校验用「报错返回」而不是抛异常——返回的字符串会直接进 tool_result,模型能据此改写
    if limit <= 0:
        return f'错误:limit 必须大于 0,收到的是 {limit}'

    return '结果文本'
```

### 五条约束

**1. 函数签名就是模型看到的参数契约。** schema 由 `inspect.signature` 自动推导，不需要手写 JSON Schema，也不要为单个工具另维护一份平行 schema。推导时排除 `self`、`agents`、`session`、`memory` 和 `**kwargs`。

**2. `**kwargs` 必须保留。** `pre_toolUse` 的 `inject_import_args` 会给**每个**工具无条件注入 `agents` / `session` / `hooks` / `Loop` / `memory`，不接住就会 `TypeError`。用得上就 `kwargs.get('session')` 取，用不上就让它被吞掉。

**3. 取注入对象时判空要「报错返回」，不要静默跳过：**

```python
session = kwargs.get('session')
if session is None:
    return '错误:该工具需要 session,但未被注入'
```

**4. `tool_autho` 决定谁能用它。** 值必须是 `agents.yaml` 里已有的授权类别（`basic_tool` / `file_read_tool` / `file_write_tool` / `command_tool` / `memory_tool` / `plan_tool` / `subagent_tool` / `web_tool` / `skill_tool` / `interaction_tool` / `mcp_tool`）。要新开一个类别，得同时在 `agents.yaml` 里给相关 Agent 补上这个键——**只写工具不改 yaml，工具对所有 Agent 都不可见**。

**5. 输出要有上限。** 工具结果整块进 session，没有上限的输出能一次顶爆模型请求。现有工具的做法可以照抄：`file_read` 有行数 / 单行 / 总字符三重上限并复用 `offset` 续读协议，`command` 有 `MAX_OUTPUT_CHARS` 的首尾保留式截断。截断时**一定要在文本里说明怎么拿到剩下的部分**，否则模型会原地重试。

---

## 加一个 Hook

### 目录骨架

```text
hook/hooks/<hook_point>/my_hook/
├── __init__.py     # 可以是空文件
└── hook.py         # 文件名必须是 hook.py
```

当前可用的 hook point：`before_session`、`pre_toolUse`、`after_round`、`after_session`。

> `before_session` 目录存在且 `main.py` 会触发它，但当前没有任何 hook 注册在上面，触发是空操作。

### 实现

```python
from hook.hook_core import hooks


@hooks.register(hook_point='after_round', background=True, enabled=True)
def my_hook(session=None, memory=None, hooks=None, **kwargs):
    # 参数按需声明并给默认值:触发方传什么由 hooks.trigger(...) 的调用点决定,
    # 声明了对方没传的参数会直接 TypeError
    if session is None:
        return
    ...
```

`@hooks.register` 的四个参数：

| 参数 | 说明 |
|---|---|
| `hook_point` | 挂在哪个事件点 |
| `background` | `True` 走后台线程池不等结果，`False` 同步执行、主循环等它返回 |
| `match` | `None` 无条件触发；`{'tool': 'file_write'}` 只在上下文匹配时触发；写成 list 表示满足任意一组即可 |
| `enabled` | 整体开关，`False` 时仍注册但永不触发 |

### 三条约束

**1. 同步还是后台，看主循环需不需要它的结果。** 需要立刻拿结果去决定下一步（比如 `session_compress` 要在下一轮之前压完）就用同步；慢且结果不影响主流程（比如切片 + 嵌入）就用后台。**后台 hook 会在退出时被 `hooks.wait_all()` 等待**，别在里面写没有超时的阻塞操作。

**2. `pre_toolUse` 可以改写工具入参**，返回 `HookResult(modify_input=tool_args)`：

```python
from hook.hook_core import hooks, HookResult


@hooks.register(hook_point='pre_toolUse')
def my_injector(tool_args, agents, session, hooks, Loop, memory=None):
    tool_args['extra'] = '...'
    return HookResult(modify_input=tool_args)
```

**3. 不要依赖注册顺序。** 自动发现按路径排序 import，但那不是可依赖的契约。有先后依赖的两件事，写进同一个函数里顺序执行——`memory_pipeline` 就是这么做的：它把「切片」和「把切片喂进 memory」合并成一个 hook，从结构上杜绝了原先两个异步 hook 靠注册顺序碰巧串行导致的读到旧数据的 bug。

---

## 加一个 Prompt 分块

### 目录骨架

```text
prompt/prompts/my_prompt/
└── prompt.py        # 文件名必须是 prompt.py,且只能在一级目录下
```

不需要 `__init__.py`。

### 实现

```python
from prompt.prompt_register import register_prompt


@register_prompt(
    prompt_name='my_prompt',
    order=25,
    condition=lambda agent: agent.agent_name == 'main',
    enabled=True,
)
def build(agent) -> str:
    return '#我的分块' + '\n\n' + '正文内容'
```

`build_prompt(agent)` 按 `order` 升序拼接，过滤掉 `enabled=False` 和 `condition` 返回假的分块，**内容为空字符串的分块也会被跳过**——所以「这次不注入」直接返回 `''` 即可，不用额外开关。

### 当前 order 分布

选 order 时对照这张表，插空即可：

```text
system_prompt      0
attachment_prompt  5
tool_prompt       10
skill_prompt      20
session_recent    30
timeline_prompt   30
memory_prompt     35
agent_prompt      40
basic_prompt      50
```

### 两条约束

**1. system prompt 是启动快照。** 分块函数在 Agent 初始化时执行一次，同一进程中后续的磁盘写入不会自动刷新 prompt。要读运行时变化的数据，得走 attachment 或工具，不能指望 prompt 分块。

**2. `condition` 收的是 agent 对象。** 常见写法是按名字（`agent.agent_name == 'main'`）或按授权（`'skill_tool' in agent.tool_autho`）过滤。

---

## 加一个技能

技能是纯 Markdown，不写代码。

```text
skill/<skill-name>/skill.md
```

```markdown
---
name: my-skill
description: "什么情况下该用这个技能。写清触发场景,这段会进 main agent 的 system prompt,模型靠它判断要不要加载。"
---

# my-skill

正文：这个技能具体怎么做。

## 步骤

1. ...
2. ...
```

**YAML frontmatter 是必需的**——`skill_prompt` 分块递归扫 `skill/**/skill.md`，跳过所有不以 `---` 开头的文件，然后只读 `name` 和 `description` 拼进 system prompt。正文要等模型调用 `skill_load` 才会被读取。

所以 `description` 决定了这个技能会不会被想起来，值得写细一点：把触发场景、典型说法都写进去，而不是只写「做 X 用这个」。

---

## 验证你的改动

```bash
python main.py
```

启动后如果新东西没生效，按这个顺序排查：

1. **工具**：`tool/tools/<name>/__init__.py` 里有没有 import 实现？`tool_autho` 的类别在 `agents.yaml` 里对目标 Agent 是不是 `true`？
2. **Hook**：文件名是不是 `hook.py`？路径里有没有下划线开头的目录段？
3. **Prompt**：是不是放在了二级目录？文件名是不是 `prompt.py`？`condition` 是不是把目标 agent 过滤掉了？
4. **技能**：`skill.md` 开头是不是 `---`？

> `python main.py` 会真实调用模型 API 并写入 session 文件，不是无副作用的冒烟测试。只想确认「注册成功了没有」的话，直接查注册表比跑完整程序快得多：

```bash
python -c "import tool; from tool.tool_core import _register; print(sorted(_register.tool_list))"
```

Hook 与 Prompt 同理，分别看 `hook.hook_core.hooks._hooks` 和 `prompt.prompt_register._register.prompt_list`。
