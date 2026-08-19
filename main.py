import signal

from session import Session
from hook.hook_core import hooks

from agent import agents
from loop import Loop
from memory import Memory
from local_model import prewarm_embedding_model, shutdown_embedding_worker
from config import MEMORY_PIPELINE_ENABLED
from mcp_client import prewarm_mcp_servers, shutdown_mcp_servers
from tui import Alear030TUI

# 嵌入在独立 worker 进程加载:此处 spawn+后台 boot(缺权重也下载+加载),不阻塞 TUI 启动
prewarm_embedding_model()

# MCP server 在后台逐个连接:连上一个就把它的工具注册进工具表并刷新各 agent 的 tool_list 快照。
# 单个 server 失败只记录不影响启动;agents 已在 import 时构造完毕,故此处能直接绑定
prewarm_mcp_servers(agents=agents)

# 创建新的memory：独立 Loop 静音 thinking 打印，避免后台 pipeline 干扰终端输出
# 管线总闸收拢在 memory 实例,开关值由 config.MEMORY_PIPELINE_ENABLED 提供。
# 注意判空在 _session_slice() 之前:关闭时切片摘要也一并短路,不只是不落盘
memory = Memory(memory_agent=agents.agents['memory'],loop=Loop(verbose=False),pipeline_enabled=MEMORY_PIPELINE_ENABLED)

# 创建新的session
session = Session(
    slice_agent=agents.agents['slice'],
    summary_agent=agents.agents['summary'],
    system_prompt=agents.agents['main'].message_list[0]['content']
)

# 创建新的Loop
loop = Loop(agents=agents,session=session,hooks=hooks,memory=memory)

AlearTui = Alear030TUI(loop=loop,session=session,hooks=hooks,agents=agents,memory=memory)

hooks.trigger(hook_point='before_session',session=session,agents=agents,memory=memory,hooks=hooks)

# 主循环入口执行程序
try:
    AlearTui.run()

finally:
    # 收尾期间忽略SIGINT，须在print/join之前装上：join不被第二下Ctrl+C打断
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    # 在退出之前进行保险环节操作
    print('[system_quit] 等待后台任务完成...')
    # after_session hooks engage
    hooks.trigger(hook_point='after_session',session=session,agents=agents,memory=memory)

    hooks.wait_all()
    hooks.shutdown()
    shutdown_mcp_servers()
    shutdown_embedding_worker()
    print('[system_quit] 任务全部完成，Alear030期待与您下次相见')
