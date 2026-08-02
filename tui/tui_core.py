from pathlib import Path

from .tui_channel import TuiChannel
from .tui_widget import TuiWidgets,tuiwidgets

from textual import on,work
from textual.app import App
from textual.widgets import Header,Footer,Static,Input
from textual.widget import Widget
from textual.containers import VerticalScroll
from textual.events import Click,Mount


# 各来源样式路径：widget 注册 css + 全局 tui_style
widget_css_files = tuiwidgets.css_files
global_css_file = str(Path(__file__).parent / 'tui_style.tcss')
css_file_paths = widget_css_files + [global_css_file]

# 入口 App：channel 路由 + 输入框 + 渲染
class Alear030TUI(App):

    TITLE = "ALEAR"

    def __init__(self,css_path=css_file_paths,loop=None,session=None,hooks=None,agents=None,memory=None):
        super().__init__(css_path=css_path)
        self.theme = "rose-pine-dawn"

        self.loop = loop
        self.session = session
        self.hooks = hooks
        self.agents = agents
        self.memory = memory

        # channel 表：agent名 -> channel
        self.channels:dict[str,TuiChannel] = {}
        # 当前对准的 channel，输入走它
        self.now_channel:TuiChannel = None
        self._channel_init()

        loop.emit_stream = self.emit_stream


    # 登记常驻 channel
    def _channel_init(self):
        main_channel = TuiChannel(channel_id=1,agent_name='main',channel_type='main_agent',channel_loop=self.loop)
        self.channels["main"]=main_channel
        # self.now_agent = self.agents.get_agent('main')
        self.now_channel = main_channel

    # 挂布局：header + main channel 滚动区 + 输入框
    def compose(self):
        yield Header(show_clock=False,name=self.TITLE)
        yield self.channels["main"].body
        yield Input(placeholder=">",id="USER_INPUT")

    # Mount 后聚焦 USER_INPUT
    @on(message_type=Mount)
    def _compose_init(self):
        self.set_focus(self.query_one("#USER_INPUT"))

    # 跑一轮：before_round → 当前 channel 的 loop → after_round
    def _run_round(self,user_input=None):
        # 空输入直接丢
        if not user_input:
            return

        agent_name = self.now_channel.agent_name

        self.hooks.trigger(hook_point='before_round',session=self.session,agents=self.agents,memory=self.memory,hooks=self.hooks,user_message=user_input)
        # 走 now_channel 绑定的 loop，按 agent_name 派发
        self.now_channel.channel_loop.loop_run(agent_name = agent_name,message = user_input)
        # pipeline_enabled=False：切片摘要可跑，不写 memory 入库
        self.hooks.trigger(hook_point='after_round',session=self.session,agents=self.agents,memory = self.memory,hooks=self.hooks,pipeline_enabled=False)

    # loop 挂载，执行中调用
    def emit_stream(self,content_type:str,stream_id:str,content:dict,agent_name:str):
        self.call_from_thread(self.channels[agent_name].append_stream,content_type=content_type,stream_id=stream_id,content=content)

    # 解锁 USER_INPUT，并重新 focus；给 finally 里 call_from_thread 回调用
    def _unlock_input(self):
        self.query_one('#USER_INPUT').disabled = False
        self.set_focus(self.query_one("#USER_INPUT"))

    # 双保险：exit_on_error=False 防 worker 异常杀 App；try 再兜一层
    @work(thread=True, exit_on_error=False)
    def do_work(self,user_input:str=None):
        try:
            self._run_round(user_input=user_input)
        except Exception:
            # @claude: do_work except 里挂 system_error widget（当前只吞异常保活），后续增加对应的SystemError Widget进行TUI渲染
            pass

        finally:
            self.call_from_thread(self._unlock_input)


    # 输入提交：内容交给当前 channel，并锁输入防连发
    @on(Input.Submitted)
    def user_input(self,event:Input.Submitted):
        inptu_content = event.value
        # 空输入直接丢
        if not inptu_content:
            return

        self.now_channel.append_once(type="UserMessage",content={"user_input":inptu_content})
        event.input.clear()
        # 锁住输入；解锁走 do_work finally
        # @claude: 后续有中途打断后，再重看这套 lock
        event.input.disabled = True

        # 挂 do_work：按当前 channel 找 agent / loop
        self.do_work(user_input = inptu_content)

if __name__ == '__main__':
    Alear030 = Alear030TUI()
    Alear030.run()
