from hook.hook_core import hooks
from eval import Trace
from log import Log

@hooks.register(
    hook_point="before_session",
    background=False,
    priority=1,
    order=1,
    enabled=True,
)
def game_begin(prompt=None,session=None,agents=None,**kwargs):
    if not prompt or not session or not agents:
        return
    
    # 非 static 的分块改走 attachment：内容跨 session 会变，留在 system prompt 里会把排在它之后的
    # 工具 schema 一起顶出 provider 的前缀缓存
    # 按 order 排序，和 build_prompt（prompt_core.py）保持同一套排序依据——不然字典插入顺序
    # （取决于 prompt/__init__.py 里目录名字母序）会让 order 字段形同虚设
    for prompt_block in sorted(prompt.prompt_list.values(),key=lambda p:p['order']):
        if prompt_block["type"] == "static" or not prompt_block["enabled"]:
            continue

        # 白名单式放行：type/target 没声明全的记账后跳过，不兜底投出，也不让下面的 "all" in target 炸穿 before_session
        if prompt_block["type"] not in ("notification","interrupt") or not prompt_block["target"]:
            Log.pending_record(level="high",source="game_begin",event="prompt_block_skip",detail={
                "prompt_name":prompt_block["name"],
                "type":prompt_block["type"],
                "target":prompt_block["target"]
            })
            continue

        # 求值一次：function 里有读盘和 tiktoken 编码，投递与 trace 两个消费者不该各调一次
        prompt_content = prompt_block["function"]()
        if not prompt_content:
            continue

        # all 展开成当前全部 agent；一条 attachment 只投一个目标，状态机才是单值的
        prompt_targets = list(agents.agents.keys()) if "all" in prompt_block["target"] else prompt_block["target"]
        for prompt_target in prompt_targets:
            session.attachment.attachment_add(
                attachment_type = prompt_block["type"],
                attachment_source = "system",
                attachment_content = prompt_content,
                attachment_target = prompt_target
            )
            Trace.trace_record(
                trace_type = "attachment_load",
                source = "system",
                trace_detail = {
                    "attachment_type" : prompt_block["type"],
                    "attachment_source" : "system",
                    "attachment_content" : prompt_content,
                    "attachment_target" : prompt_target
                }
            )
