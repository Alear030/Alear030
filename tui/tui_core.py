from pathlib import Path

from .tui_channel import TuiChannel
from .tui_widget import tuiwidgets

from textual import on,work
from textual.app import App
from textual.events import Click, Mount

# 全局变量
_UserInput = tuiwidgets.widget_list["UserInput"]["widget_cls"]
# 各来源样式路径：widget 注册 css + 全局 tui_style
widget_css_files = tuiwidgets.css_files
global_css_file = str(Path(__file__).parent / 'tui_style.tcss')
css_file_paths = widget_css_files + [global_css_file]



# 入口 App：channel 路由 + 输入框 + 渲染
class Alear030TUI(App):

    TITLE = "ALEAR"

    def __init__(self,css_path=css_file_paths,loop=None,session=None,hooks=None,agents=None,memory=None):
        super().__init__(watch_css=True,css_path=css_path,ansi_color=True)
        self.theme = "textual-dark"

        self.loop = loop
        self.loop.emit = self.receive_loop_emit
        self.session = session
        self.hooks = hooks
        self.agents = agents
        self.memory = memory

        # channel 表：agent名 -> channel
        self.channels:dict[str,TuiChannel] = {}
        # 当前对准的 channel，输入走它
        self.now_channel:TuiChannel = None
        self._channel_init()

        # channel下的状态占位栏、用户输入栏、提示栏
        # @claude 后续再做吧，先集中注意力在tool_call_widgets上面
        self.user_input = tuiwidgets.build_widget(widget_type="UserInput",widget_id="USER_INPUT",widget_content={"placeholder":""})


    # 登记常驻 channel
    def _channel_init(self):
        main_channel = TuiChannel(channel_id=1,agent_name='main',channel_type='main_agent',channel_loop=self.loop)
        self.channels["main"]=main_channel
        # self.now_agent = self.agents.get_agent('main')
        self.now_channel = main_channel

    # 挂布局：header + main channel 滚动区 + 输入框
    def compose(self):
        yield self.channels["main"].body
        yield self.user_input

    # @claude 一次性渲染不再需要独立 emit_once 方法：loop 侧 emit 泛化后，新增一次性事件（如 system_message）经事件分发路由 channel.append_once 即可


    # Mount 后聚焦 USER_INPUT
    @on(message_type=Mount)
    def _compose_init(self):
        self.user_input._set_focus()

    # 保持焦点永远在user_input上
    @on(Click)
    def _focus_on_user_input(self,event:Click):
        if self.user_input.display and not self.user_input.disabled:
            self.user_input._set_focus()
        return
    
    # 输入提交：内容交给当前 channel，并锁输入防连发
    @on(_UserInput.Submitted)
    def _user_input_submitted(self,event:_UserInput.Submitted):
        inptu_content = event.value
        # 空输入直接丢
        if not inptu_content:
            return
        # 触发 UserContent 挂载，并传入 stream_id
        self.user_input._clear()
        self.now_channel.append_once(content_type="UserContent",content={"user_input":inptu_content})
        # 新一轮：Textual anchor贴底
        self.now_channel.body.stick_bottom()
        # 锁住输入；解锁走 do_work finally
        self.user_input._set_disabled(True) # @claude: 后续有中途打断后，再重看这套 lock
        # 挂 do_work：按当前 channel 找 agent / loop
        self.do_work(user_input = inptu_content)

    # 双保险：exit_on_error=False 防 worker 异常杀 App；try 再兜一层
    @work(thread=True, exit_on_error=False)
    def do_work(self,user_input:str=None):
        try:
            self._run_round(user_input=user_input)
        except Exception:
            # @claude: do_work except 里挂 system_error widget（当前只吞异常保活），后续增加对应的SystemError Widget进行TUI渲染
            pass

        finally:
            self.call_from_thread(self.user_input._set_disabled,False)
            self.call_from_thread(self.user_input._set_focus)
            # 异常也收尾：下一轮前再贴底
            self.call_from_thread(self.now_channel.body.stick_bottom)

    # 跑一轮：before_round → 当前 channel 的 loop → after_round
    def _run_round(self,user_input:str=None):
        # 空输入直接丢
        if not user_input:
            return
        
        agent_name = self.now_channel.agent_name
        # 触发 before_round 钩子
        self.hooks.trigger(hook_point='before_round',session=self.session,agents=self.agents,memory=self.memory,hooks=self.hooks,user_message=user_input)
        # 走 now_channel 绑定的 loop，按 agent_name 派发
        self.now_channel.channel_loop.loop_run(agent_name = agent_name,message = user_input)
        # 入库开关收拢在 memory.pipeline_enabled(创建时统一设置),触发时不再传
        self.hooks.trigger(hook_point='after_round',session=self.session,agents=self.agents,memory = self.memory,hooks=self.hooks)

        # 本轮流式结束：下一轮前再贴底（正常路径；异常靠do_work finally）
        self.call_from_thread(self.now_channel.body.stick_bottom)


    def receive_loop_emit(self,event:str=None,content:dict=None,agent_name:str=None,stream_id:str=None):
        if agent_name not in self.channels.keys():
            return # @claude 后续增加System_error widget展示错误
        target_channel = self.channels[agent_name]
        self.call_from_thread(target_channel.handle_loop_emit,event=event,content=content,agent_name=agent_name,stream_id=stream_id)
