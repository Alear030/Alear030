from session import Session
from hook.hook_core import hooks

from agent import agents
from loop import Loop
from memory import Memory
from local_model import prewarm_embedding_model, shutdown_embedding_worker
from tui import Alear030TUI

# 嵌入在独立 worker 进程加载:此处只 spawn+异步 warmup,不阻塞 TUI 启动;
# 权重缺失时跳过(不在后台静默下 195MB);缺权重提示改由 TUI Mount 后可见展示
prewarm_embedding_model()

# 创建新的memory：独立 Loop 静音 thinking 打印，避免后台 pipeline 干扰终端输出
memory = Memory(memory_agent=agents.agents['memory'],loop=Loop(verbose=False))

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

except KeyboardInterrupt:
    # 检测到退出动作，进行收尾
    print('\n[system_quit] 接收到退出动作，正在处理后台运行任务请稍等...')

finally:
    # 在退出之前进行保险环节操作
    print('[system_quit] 等待后台任务完成...')
    # after_session hooks engage
    hooks.trigger(hook_point='after_session',session=session,agents=agents,memory=memory)

    hooks.wait_all()
    hooks.shutdown()
    shutdown_embedding_worker()
    print('[system_quit] 任务全部完成，Alear030期待与您下次相见')
