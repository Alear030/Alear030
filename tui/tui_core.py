import signal
import threading

from pathlib import Path

from .tui_channel import TuiChannel
from .tui_widget import tuiwidgets

from textual import on,work
from textual.app import App
from textual.events import Click, Mount
from textual.binding import Binding

# 全局变量
_UserInput = tuiwidgets.widget_list["UserInput"]["widget_cls"]
# 各来源样式路径：widget 注册 css + 全局 tui_style
widget_css_files = tuiwidgets.css_files
global_css_file = str(Path(__file__).parent / 'tui_style.tcss')
css_file_paths = widget_css_files + [global_css_file]



# 入口 App：channel 路由 + 输入框 + 渲染；inherit_bindings=False 丢掉 App 自带 ctrl+q
class Alear030TUI(App,inherit_bindings=False):

    TITLE = "ALEAR"

    # 关掉命令面板，避免 ctrl+p 另开退出入口
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        # 抢 ctrl+c：有选区复制，无选区退出
        Binding("ctrl+c", "ctrl_c_event",show=False,priority=True)
    ]

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
        self.bottom_bar = tuiwidgets.build_widget(widget_type="BottomBar",widget_id="BOTTOM_BAR",widget_content={"state":"default"})

    # 登记常驻 channel
    def _channel_init(self):
        main_channel = TuiChannel(channel_id=1,agent_name='main',channel_type='main_agent',channel_loop=self.loop)
        self.channels["main"]=main_channel
        # self.now_agent = self.agents.get_agent('main')
        self.now_channel = main_channel

    # 挂布局：header + main channel 滚动区 + 输入框
    def compose(self):
        yield self.channels["main"].body
        yield self.bottom_bar

    # Mount 后聚焦 USER_INPUT
    @on(message_type=Mount)
    def _compose_init(self):
        self.bottom_bar.always_on_focus()

    # 保持焦点永远在user_input上
    @on(Click)
    def _focus_on_user_input(self,event:Click):
        self.bottom_bar.always_on_focus()
        return
    
    # 输入提交：内容交给当前 channel，并锁输入防连发
    @on(_UserInput.Submitted)
    def _user_input_submitted(self,event:_UserInput.Submitted):
        inptu_content = event.value
        # 空输入直接丢
        if not inptu_content:
            return
        # 触发 UserContent 挂载，并传入 stream_id
        self.bottom_bar.UserInput_clear()
        self.now_channel.append_once(content_type="UserContent",content={"user_input":inptu_content})
        # 新一轮：Textual anchor贴底
        self.now_channel.body.stick_bottom()
        # 锁住输入；解锁走 do_work finally
        self.bottom_bar.UserInput_set_disabled(True) # @claude: 后续有中途打断后，再重看这套 lock
        # 挂 do_work：按当前 channel 找 agent / loop
        self.do_work(user_input = inptu_content)

    # 双保险：exit_on_error=False 防 worker 异常杀 App；try 再兜一层
    @work(thread=True, exit_on_error=False)
    def do_work(self,user_input:str=None):
        try:
            self._run_round(user_input=user_input)
        except Exception as ee:
            self.call_from_thread(
                self.now_channel.append_once,
                content_type="SystemError",
                content={"message":f"{type(ee).__name__}: {ee}"},
            )

        finally:
            self.call_from_thread(self.bottom_bar.UserInput_set_disabled,False)
            self.call_from_thread(self.bottom_bar.UserInput_set_focus)
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


    # loop 外发入口：未知 agent 兜底；底栏 event 先截；其余丢给对应 channel
    def receive_loop_emit(self,event:str=None,content:dict=None,agent_name:str=None,stream_id:str=None):
        # 底栏认领的 event 先截走，不进 channel；UI 线程直接调，别 call_from_thread
        method_name = self.bottom_bar.event_methods.get(event,None)
        if method_name is not None:
            method = getattr(self.bottom_bar,method_name)
            if self._thread_id == threading.get_ident():
                method(content=content)
            else:
                self.call_from_thread(method,content=content)
            return

        if agent_name not in self.channels.keys():
            # done(@claude): 未知 agent 挂 SystemError 到 now_channel，不再静默 return
            self.call_from_thread(
                self.now_channel.append_once,
                content_type="SystemError",
                content={"message":f"未知 agent_name: {agent_name}"},
            )
            return

        # 其余按 agent_name 丢给对应 channel
        target_channel = self.channels[agent_name]
        self.call_from_thread(target_channel.handle_loop_emit,event=event,content=content,agent_name=agent_name,stream_id=stream_id)


    # BINDINGS 入口：有选区复制，无选区 App.exit
    def action_ctrl_c_event(self):
        # 如果程序已经退出，则直接返回
        if self._exit:
            return
        
        # Input 选区走 selected_text；消息区鼠标拖选用 screen.get_selected_text
        selected = getattr(self.focused,"selected_text",None) or self.screen.get_selected_text() or ""
        if selected:
            self.copy_to_clipboard(selected)
            return
        
        # 如果没有选取内容，进入确认退出流程
        if not self.bottom_bar.exit_confirm_status:
            self.receive_loop_emit(event="ExitConfirm",content={})
            return

        # 如果没有触发上述的事件，则退出程序
        self.exit()
    
    # 主线程SIGINT：call_later丢回消息循环，不用call_from_thread
    def _dispatch_ctrl_c(self,signum,frame):
        if not self.call_later(self.action_ctrl_c_event):
            self.exit()
    
    # TUI 存活期：SIGINT 转到 ctrl+c 同一套复制/退出
    def run(self,*args,**kwargs):
        signal.signal(signal.SIGINT,self._dispatch_ctrl_c)
        try:
            return super().run(*args,**kwargs)
        except KeyboardInterrupt:
            return
        finally:
            # 收尾期：忽略SIGINT，别还默认handler打断main收尾
            signal.signal(signal.SIGINT,signal.SIG_IGN)