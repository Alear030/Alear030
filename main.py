from session import Session
from hook.hook_core import hooks

from agent import agents
from loop import Loop
from memory import Memory
from tui import Alear030Tui

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
    hooks.trigger(hook_point='after_round',session=session,agents=agents,memory = memory,hooks=hooks)
    return result

alearTui = Alear030Tui(run_round=run_round)
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