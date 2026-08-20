---
name: alear030-verify
description: "Alear030 项目里验证代码改动是否可用时使用。这个项目的验证方式有几个反直觉的坑:python main.py 在主仓库不是无副作用的冒烟测试(会写 session 文件、可能调模型 API),但在关闭了 memory pipeline 的开发 worktree 里可以放开跑——先分清自己在哪个 checkout 再决定松紧;验证脚本必须用 python -m 点号路径调用,直接 python test/xxx/script.py 会报 ModuleNotFoundError;unittest discover 不能带 -s test 参数,否则 test/loop/__init__.py 会遮蔽顶层 loop 包报 ImportError。当准备验证改动、跑测试、或纠结要不要真跑 main.py 时用这个 skill,别凭经验直接跑通用 Python 项目的验证套路。"
---

# Alear030 验证方式

这个项目的验证套路和常规 Python 项目不一样,踩坑点集中在"哪些命令能跑""跑起来会不会有副作用"上。改完代码想验证时,先按下面的判断走,别凭经验直接套通用套路。

## 判断 0:先分清你在哪个 checkout

**这一步决定后面所有条款的松紧,必须先判。** 同一份代码在主仓库和在开发 worktree 里,验证能放开到什么程度完全不同。

判据看配置,不看路径名:

```bash
grep -n "MEMORY_PIPELINE_ENABLED" config.py
ls memory/memory_storage/memory_storages/
```

- `MEMORY_PIPELINE_ENABLED = False`,且 `memory_storages/` 为空 → **开发 worktree**,走宽松档
- `MEMORY_PIPELINE_ENABLED = True`,或 `memory_storages/` 里有真实数据 → **主仓库**,走严格档

**不要用「路径里有没有 `worktrees`」来判。** 未来完全可能出现开着 pipeline 的 worktree,路径名会骗人,配置不会。

### 宽松档(开发 worktree)

`pipeline_enabled=False` 让 memory 分类、user_info、task 落盘全部短路,跑什么都不会污染真实记忆。所以:

- `python main.py` 可以直接跑,不用先纠结值不值得
- 可以随便写 session 文件、反复跑到底
- **不需要**在测试前后算 MD5 比对
- 探针脚本不必跑完即删,想留在 `test/` 下就留着

想怎么测就怎么测——这个 checkout 就是拿来试的。

### 严格档(主仓库)

见文末「处理运行数据时的额外红线」,整节适用。

### 两档共同的底线

**不批量删除或清空 `session/session_detail/`。** 它已被 `.gitignore`,删了不可恢复;而且历史 session 是排查问题时唯一的现场证据——查某个工具的真实行为、复盘模型当时的决策链,全靠它。单个临时 session 文件可以删,整目录清场不行。

## 判断:要验证到什么程度

先分清三个层次,选够用的那一层就好,不用每次都跑到最重的那一层:

1. **只想确认语法能解析**(改动小、不涉及逻辑分支)→ 用下面的 AST 检查命令
2. **想验证某个具体逻辑**(比如某个 prompt 拼装函数、某个 slice 判断)→ 写探针脚本或跑对应 `test/` 下的单测,用 `python -m` 点号路径调用
3. **想端到端验证整条链路**→ 先按判断 0 分清 checkout:worktree 里直接跑 `python main.py`;主仓库则先评估副作用

## 1. 低副作用语法检查(AST 解析)

不会导入项目、不会调用模型 API、不会生成 `.pyc`,只证明源码能被解析:

```bash
python -c "import ast,pathlib; excluded={'workspace','z_ccstudy','z_old_code','.venv'}; files=[p for p in pathlib.Path('.').rglob('*.py') if not any(part in excluded for part in p.parts)]; [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print(f'AST OK: {len(files)} files')"
```

这只证明源码可解析,**不等价于依赖、模块注册或端到端行为验证**。改完就下结论"语法没问题"之前,想清楚这次改动是不是真的只需要语法层验证。

## 2. 跑单测或探针脚本:必须用 `python -m` 点号路径

`import` 项目内部模块会触发 hook/prompt/tool 三套自动发现的装饰器注册,打印一串 `tool X loaded...` / `prompt Y loaded...`——这是注册副作用,不是错误,别据此判断改动出了问题。

验证脚本必须从仓库根目录用点号路径调用,**不带 `.py` 后缀**:

```bash
python -m test.interaction.test_ask_user_question
```

直接 `python test/xxx/script.py` 即使 cwd 在根目录也会报 `ModuleNotFoundError`,因为 Python 会把脚本自身所在目录塞进 `sys.path[0]`,不是 cwd。

**前置:`test/` 必须有 `__init__.py` 才能用 `python -m test.xxx`**。项目 `test/` 无 `__init__.py` 时是命名空间包,会被 stdlib 自带的 `test` 包(如 `Python311\Lib\test`)抢先,`python -m test.xxx` 报 `No module named 'test.xxx'`。在 `test/` 下放一个空的 `__init__.py` 让项目 `test` 成常规包(cwd 在 sys.path[0],优先于 stdlib)即可。注意 `test/` 已整体纳入 `.gitignore`,这个 `__init__.py` 不进版本控制,每个 worktree/checkout 要本地确保存在(没有就建一个空的)。

跑全部单测时**不要带 `-s test`**:

```bash
python -m unittest discover
```

`python -m unittest discover -s test` 会因为 `test/loop/__init__.py` 遮蔽顶层 `loop` 包而报 `ImportError: cannot import name 'Loop'`。

## 3. 低成本探测模型决策点(不想承受 main.py 副作用时)

如果只是想看模型在某个具体决策点(该不该调某个工具、该不该先读技能内容等)会怎么反应,又不想真跑 `main.py` 触发 `ask_user_question` 阻塞 `input()`、真的写文件、真的派 subagent,可以绕开 Loop/session/hooks,直接拿常驻 Agent 手工拼消息:

```python
agents.agents['main'].agent_ai.chat.completions.create(
    model=agents.agents['main'].model_name,
    messages=[...],
    tools=agents.agents['main'].tool_list,
    tool_choice='auto',
    extra_body={'thinking': {'type': 'enabled'}},
)
```

只看第一个 `tool_call` 是否符合预期就行。**在主仓库,这类探针脚本连同输出文件跑完即删,不要留在 `test/` 下**;开发 worktree 里不必,想留就留(见判断 0)。

## 4. 端到端跑 `python main.py`

**在主仓库,它不是无副作用的冒烟测试**:

- `Session()` 启动时就创建 `session/session_detail/<session_id>.json`
- 每次交互和退出收尾都可能调用模型 API
- 会更新 session、memory storage 和 memory config

**在开发 worktree(判断 0 的宽松档),上面第三条不成立**——`pipeline_enabled=False` 让 memory 落盘短路,只剩 session 文件和 API 调用两项开销,想跑就跑,不用先权衡。

当前已有局部 `unittest`,但没有覆盖运行主流程的成体系测试套件。**按改动位置运行对应测试,不要假设 `test/` 中每一项都能直接执行**——有些是 backfill/diagnose 类一次性脚本,不是常规单测。

## 5. 排查失败与编码坑点

`unittest discover` 跑出失败时，先用 `git stash` 回退到改动前的代码重跑一次：如果失败照样复现，说明是历史遗留的断言漂移（测试没跟上生产代码的既有行为变更），与本次改动无关，不必现场修复；只有 stash 前不失败、stash 后（=当前改动下）才失败的才是本次改动引入的问题。项目里已有若干这类历史遗留失败（测试断言停留在生产代码演进前的旧行为）。

在 Windows 上用 `Path.read_text()`/`write_text()` 读写项目里的中文 JSON/文本文件时必须显式传 `encoding='utf-8'`；不传会走系统默认 GBK 码页，遇到中文内容直接 `UnicodeDecodeError`。这个坑在 prompt/memory 相关模块的文件读写点上出现过不止一次。

## 处理运行数据时的额外红线(主仓库适用)

**先按判断 0 确认自己在主仓库。** 开发 worktree 里这一节整体不适用,只保留「不批量删 `session_detail`」那条共同底线。

如果验证过程需要读写 `session/session_detail/`、`session/session_plan/`、`memory/memory_storage/`、`memory/memory_config/`、`memory/memory_log/`、`local_model/` 这几个目录:

- 这些目录存的是真实运行数据,不是可随意重建的临时文件
- 需要干净环境验证时用临时目录或临时 session id,不得清场式测试真实数据
- 用真实历史数据重放验证改动(比如测试新版 prompt)时,测试前后对相关文件计算 MD5 并比对,证明测试脚本没有意外写入
- 测试脚本本身及其输出落在 `test/` 下的临时文件,跑完清理掉,不落进正式 `memory_storage`/`session_detail`
