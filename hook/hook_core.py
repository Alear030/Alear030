from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any,Callable

from core.rich_output import rich_print

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
    background: bool = False #True=后台线程异步跑，主循环不等它,False=同步跑，主循环等它执行完
    match: dict | list[dict] | None = None # None=不筛选，什么场景都触发 {"tool": "write_file"}=只匹配名为 write_file 的工具


# ═══════════════════════════════════════════════════════════
# HookManager —— 钩子管理器
# 内部结构:
#   self._hooks = {
#       "PostTurn":    [HookDef(切片钩子), HookDef(审批提醒钩子)],
#       "PreToolUse":  [HookDef(写保护钩子)],
#   }
# 核心方法:
#   register()  → 把一个函数注册为钩子（用装饰器 @ 语法）
#   trigger()   → 拽某个插孔上的所有匹配钩子
#   _match()    → 判断钩子的 match 条件和当前场景是否匹配
#   collect()   → 非阻塞看一眼后台任务
#   wait_all()  → 阻塞等全部后台任务跑完
#   shutdown()  → 关闭线程池
# ═══════════════════════════════════════════════════════════
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
        # Future 对象 = 线程池的"外卖单号"，可以查跑完了没
        self._pending: list[tuple[str,Any]] = []


    def register(self,hook_point:str,background:bool=False,match:dict|None=None):
        # 检查hook_point是否存在,不存在就添加上该hook_point
        if hook_point not in self._hooks:
            self._hooks[hook_point] = []

        # 处理函数
        def add_hook(func):
            # 富输出hook创建
            rich_print(f'hook {func.__name__} loaded...',type='system_message')
            
            hook_def = HookDef(func=func,background=background,match=match)
            self._hooks[hook_point].append(hook_def)
            return func
        
        return add_hook
    

    def trigger(self,hook_point:str,match_ctx:dict|None=None,**kwargs)->list[HookResult]:
        # hook_point：触发时机  match_ctx：匹配条件  **kwargs：冗余参数垃圾袋
        results:list[HookResult] = []

        # 拿到这个插孔上的所有钩子，没有就返回空列表什么都不做
        for hook_def in self._hooks.get(hook_point,[]):

            # match 筛选 判断是否存在match条件，如果存在则对比match的key和value是否完全匹配
            if not self._match(hook_def,match_ctx):
                continue
            
            # 后台钩子，放入线程池，拿到future对象并记录到_pedding中，不等结果，继续主循环
            if hook_def.background:
                future = self._pool.submit(hook_def.func,**kwargs)
                self._pending.append((hook_def.func.__name__,future))
            
            # 同步钩子，当场执行并得到结果，同时打印异常保持不崩
            else:
                try:
                    result = hook_def.func(**kwargs)
                    if isinstance(result,HookResult):
                        results.append(result)
                except Exception as ee:
                    print(f"[Hook error] {hook_def.func.__name__} 异常 : {ee}")

        return results # 返回所有同步钩子的HookResult进行处理
    

    def _match(self,hook_def:HookDef,ctx:dict|None)->bool:

        if hook_def.match is None:# 没设条件 → 无条件触发
            return True 
        
        if ctx is None: # 设了条件但没传 ctx → 不触发
            return False
        
        # 逐个 key 比对，全相等才算匹配。list 类型时任一子条件匹配即可
        if isinstance(hook_def.match, list):
            return any(all(ctx.get(k) == v for k, v in m.items()) for m in hook_def.match)
        return all(ctx.get(key) == value for key, value in hook_def.match.items())
    

    def collect(self):
        # 把已经完成的后台任务移走，不阻塞只是看一眼
        self._pending = [(name,fut) for name,fut in self._pending if not fut.done()]
    
    
    def wait_all(self):
        # 阻塞等全部后台任务跑完 通常用在程序退出前，确保所有后台切片/压缩都写盘了，在用户control_c之前调用
        for name,future in self._pending:
            try:
                # future.result() 会阻塞直到那个任务完成
                future.result()
            except Exception as ee:
                print(f"[Hook error] 后台 {name} 异常 : {ee}")


    def shutdown(self):
        # shutdown(): 关闭线程池,wait=True: 等正在跑的任务跑完再关，在用户control_c之前调用
        self._pool.shutdown(wait=True)


# 创建全局hook实例
hooks = HookManager()
