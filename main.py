import signal

from hook import hooks
from agent import agents
from prompt import prompt

from session import Session
from loop import Loop
from memory import Memory
from tui import Alear030TUI
from eval import Trace
from log import Log

from config import MEMORY_PIPELINE_ENABLED

from local_model import prewarm_embedding_model, shutdown_embedding_worker
from mcp_client import prewarm_mcp_servers, shutdown_mcp_servers

# 嵌入在独立 worker 进程加载:此处 spawn+后台 boot(缺权重也下载+加载),不阻塞 TUI 启动
prewarm_embedding_model()

# main重构，各个模块重构
# 梳理全局的引用链路和构造顺序以及各个模块的边界
# 首先原则是：
#   各个模块之间不能相互直接import引用
#   各个模块之间应该直接暴露自身的能力接口而非让别的实例直接持有或者改变另一实例中的自身属性
#   各个实例之间不能相互持有“朋友的朋友”的方法，也别直接使用！！！！
#   各个实例和模块之间最好通过hook来相互通信，这条目前不确定，不然到后续改东西就得去hook挨个找了
#   然后就是装配和持有以及触发别混合到一起，不然整个项目都得重新写一遍我操！！！！

for agent in agents.agents.values():
    agent_system_prompt = prompt.build_prompt(agent=agent)
    agent.message_list = [{"role":"system","content":agent_system_prompt}]

# MCP server 后台逐个连接:连上一个就注册进工具表并刷新各 agent 的 tool_list 快照,单个失败只记录不挡启动
# 必须传 agents:不传工具只进注册表,进不了 agent 构造期那份快照,模型永远看不到
prewarm_mcp_servers(agents=agents)

session = Session(
    slice_agent=agents["slice"],
    summary_agent=agents["summary"],
    system_prompt=agents.agents["main"].message_list[0]["content"]# @claude 这里不对 session不应该持有main agent的system_prompt
)

Log(log_id=session.session_id)
Trace(trace_id=session.session_id)

memory = Memory(
    memory_agent=agents.agents["memory"],
    loop=Loop(verbose=False),
    pipeline_enabled=MEMORY_PIPELINE_ENABLED
)

loop = Loop(
    agents=agents,
    session=session,
    hooks=hooks,
    memory=memory
)

AlearTui = Alear030TUI(
    loop=loop,
    session=session,
    hooks=hooks,
    agents=agents,
    memory=memory
)


# 主循环入口执行程序
try:
    hooks.trigger(hook_point='before_session',prompt=prompt,session=session,agents=agents)
    AlearTui.run()

finally:
    # 收尾期间忽略SIGINT，须在print/join之前装上：join不被第二下Ctrl+C打断
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    # 在退出之前进行保险环节操作
    print('[system_quit] 等待后台任务完成...')

    # after_session hooks engage
    Trace.trace_record(trace_type="after_session",source="hook",trace_detail={"status":"hook_on"})
    hooks.trigger(hook_point='after_session',session=session,agents=agents,memory=memory)
    hooks.wait_all()
    hooks.shutdown()
    Trace.trace_record(trace_type="after_session",source="hook",trace_detail={"status":"hook_done"})

    shutdown_mcp_servers()
    shutdown_embedding_worker()

    Trace.trace_end()
    print('[system_quit] 任务全部完成，Alear030期待与您下次相见')
