from session import Session
from hook.hook_core import hooks

from agent import agents
from loop import Loop
from memory import Memory
from tui import Alear030Tui
from local_model import prewarm_embedding_model

# 嵌入模型预热:切片/摘要是第一批用到它的调用,懒加载那 8.6s 不该算进第一轮会话链路;
# 权重缺失时不预热(不在后台静默下 195MB);缺权重提示改由 TUI Mount 后可见展示
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

hooks.trigger(hook_point='before_session',session=session,agents=agents,memory=memory,hooks=hooks)
def run_round(message:str)->str:
    # 执行before_round hook
    hooks.trigger(hook_point='before_round',session=session,agents=agents,memory=memory,hooks=hooks,user_message=message)
    # 执行loop
    result = loop.loop_run(agent_name='main',message=message)
    # 执行after_round hook
    hooks.trigger(hook_point='after_round',session=session,agents=agents,memory = memory,hooks=hooks,pipeline_enabled=False)
    return result

# 将loop和session传入TUI用于展示相关信息
# 启动前刷一次 token,让首屏 status 就有 system prompt 用量,不必等第一轮 after_round
session._session_count_tokens(agents.agents['main'])
alearTui = Alear030Tui(run_round=run_round,session=session)

# 主循环入口执行程序
try:
    alearTui.run()

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
    print('[system_quit] 任务全部完成，Alear030期待与您下次相见')