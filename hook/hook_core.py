from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any,Callable

from rich_output import rich_print

# HookResult —— 钩子的返回值，决定主流程怎么响应
@dataclass
class HookResult:
    block: bool = False # 阻止后续动作（如阻止工具执行）
    block_reason: str = '' # 阻止原因，主循环打印给用户看
    inject_content: dict[str,str] |None = None # 非空时，主循环把这段话拼进message_list
    modify_input:dict | None = None # 非空时，主循环用这个值替换工具的入参


# HookDef —— 一个钩子的包装
@dataclass
class HookDef:
    func: Callable #钩子函数本身
    background: bool = False #True=后台线程异步跑不等结果，False=同步跑等待完成
    match: dict | list[dict] | None = None # None=无条件触发 {"tool": "write_file"}=只匹配该工具
    enabled: bool = True # 整体开关，False时该钩子仍注册但永不触发（对应tool的tool_enabled、prompt的enabled）


class HookManager:
    def __init__(self,max_workers:int = 1):
        # 所有注册的钩子，按 hook_point 分组
        # {
        # "PostTurn":    [HookDef(切片钩子), HookDef(审批钩子)],
        # "PreToolUse":  [HookDef(写保护钩子)],
        # }
        self._hooks : dict[str,list[HookDef]] = {}

        # 后台线程池: 1 个线程，给 background=True 的钩子排队用
        self._pool = ThreadPoolExecutor(max_workers=max_workers)

        # 正在跑的后台任务: [(钩子名, Future对象)]
        self._pending: list[tuple[str,Any]] = []


    def register(self,hook_point:str,background:bool=False,match:dict|None=None,enabled:bool=True):
        if hook_point not in self._hooks:
            self._hooks[hook_point] = []

        def add_hook(func):
            status = '' if enabled else ' (disabled)'
            rich_print(f'hook {func.__name__} loaded{status}...',type='system_message')
            hook_def = HookDef(func=func,background=background,match=match,enabled=enabled)
            self._hooks[hook_point].append(hook_def)
            return func

        return add_hook


    # 主循环在某个时机点（如 after_round、pre_toolUse）调这个方法，
    # 意思是"通知所有挂在这个点上的钩子：这件事发生了"。
    # match_ctx 是这次事件的上下文，比如 pre_toolUse 时传 {"tool": "write_file"}，
    # 用来筛选出真正关心这次事件的钩子（见 _match）。
    # **kwargs 是钩子函数实际需要的参数（session、tool_input 等），原样转发。
    def trigger(self,hook_point:str,match_ctx:dict|None=None,**kwargs)->list[HookResult]:
        results:list[HookResult] = []

        for hook_def in self._hooks.get(hook_point,[]):

            # 放在 _match 和 submit 之前：禁用的后台钩子不能进线程池，否则 wait_all 退出时还要等它
            if not hook_def.enabled:
                continue

            if not self._match(hook_def,match_ctx):
                continue

            # background=True：不关心结果，也不能让它拖慢主循环（比如切片+embedding很慢），
            # 丢进线程池就算完事，future 存到 _pending 里，之后靠 collect/wait_all 收尾。
            if hook_def.background:
                future = self._pool.submit(hook_def.func,**kwargs)
                self._pending.append((hook_def.func.__name__,future))

            # background=False：主循环需要立刻拿到结果去决定下一步（比如是否阻止工具执行），
            # 所以当场跑、当场等。钩子内部报错不能让主流程崩，所以这里吞掉异常只打印。
            else:
                try:
                    result = hook_def.func(**kwargs)
                    if isinstance(result,HookResult):
                        results.append(result)
                except Exception as ee:
                    print(f"[Hook error] {hook_def.func.__name__} 异常 : {ee}")

        return results # 只包含同步钩子的结果，主循环拿这个列表去做block/inject等处理


    # 判断这个钩子该不该在这次事件里触发。
    # hook_def.match 是注册时声明的"我只关心什么场景"，ctx 是这次事件实际发生的场景。
    def _match(self,hook_def:HookDef,ctx:dict|None)->bool:

        if hook_def.match is None:# 没设条件 → 无条件触发
            return True

        if ctx is None: # 设了条件但没传 ctx → 不触发
            return False

        # match 写成 list 时表示"满足其中任意一组条件就算匹配"（多个场景复用同一个钩子）；
        # 单个 dict 时要求这组条件里的每个 key 都对得上（一个不满足就不匹配）
        if isinstance(hook_def.match, list):
            return any(all(ctx.get(k) == v for k, v in m.items()) for m in hook_def.match)
        return all(ctx.get(key) == value for key, value in hook_def.match.items())


    def collect(self):
        # 移除已完成的后台任务，不阻塞
        self._pending = [(name,fut) for name,fut in self._pending if not fut.done()]


    def wait_all(self):
        # 阻塞等全部后台任务跑完，退出前调用确保切片/压缩都写盘（Ctrl+C 前）
        for name,future in self._pending:
            try:
                future.result()
            except Exception as ee:
                print(f"[Hook error] 后台 {name} 异常 : {ee}")


    def shutdown(self):
        # 关闭线程池并等待在跑任务结束（Ctrl+C 前调用）
        self._pool.shutdown(wait=True)


# 创建全局hook实例
hooks = HookManager()
