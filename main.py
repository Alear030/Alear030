from core import loop
from session import Session
from hook.hook_core import hooks

from agent import agents

# 创建slice_subagent & summary_subagent
# main_agent = Agent(agent_id=int(0),agent_name='main',agent_role='main',agent_mode='auto')
# slice_agent = Agent(agent_id=int(1),agent_name='slice',agent_role='slice',agent_mode='auto')
# summary_agent = Agent(agent_id=int(2),agent_name='summary',agent_role='summary',agent_mode='auto')

# 创建新的session
session = Session(slice_agent=agents.agents['slice'],summary_agent=agents.agents['summary'])


try:
    while True:
        # 用户输入信息并传入loop
        user_message = input('please enter your message: ')
        
        # 开启本轮循环
        loop(session=session,agents=agents,user_message=user_message,hooks=hooks)
        
        # 一轮对话完毕之后，对话round增加
        session.round += 1
        
        # 一轮对话完毕之后，执行回合完毕的hooker：session_slice,session_compress
        hooks.trigger(hook_point='round_finished',session=session,agents=agents)
        hooks.collect()

except KeyboardInterrupt:
    # 检测到退出动作，进行收尾
    print('\n[system_quit] 接收到退出动作，正在处理后台运行任务请稍等...')

finally:
    # 在推出之前进行保险环节操作
    print('[system_quit] 等待后台任务完成...')
    hooks.wait_all()
    hooks.shutdown()
    print('[system_quit] 任务全部完成，Alear030期待与您下次相见')