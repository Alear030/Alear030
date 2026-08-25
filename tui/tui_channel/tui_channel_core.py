from ..tui_widget import tuiwidgets


from contextlib import _AsyncGeneratorContextManager
from dataclasses import dataclass

from textual.containers import VerticalScroll,Horizontal
from textual.widgets import Static


# DOM窗口化尝试记录（20260825回退，完整实现存档在本地分支tui-channel-window）
# 曾在这里做过窗口化：body_log存全量快照，DOM只挂视口上下各约1.5屏内的真widget，
# 出窗删、进窗按restore_content重建，窗外累计高度由上下两个spacer吃掉稳住virtual_size。
# 回退不是因为没跑通，是代价错位——重建要求channel侧长期维护一份与widget平行的
# restore_content，每新增一种流式widget都得回这里补一条合并规则，widget注册体系
# 「加widget只碰自己目录」的局部性被打破；自管跟随态则是在重写Textual已有的机制。
# 下次真要做，这几条是当时踩出来的：
#   1. 零高spacer仍参与布局，会把相邻消息的单次margin折叠拆成两段、凭空多出一行；
#      必须同时置display=False才不进arrange
#   2. anchor()靠 scroll_y >= max_scroll_y 复位锚点（Widget._check_anchor），窗口化让
#      virtual_size天然抖动就会打坏它，被迫自造跟随态——那是复杂度的主要来源
#   3. watch_virtual_size触发时max_scroll_y尚未按新布局重算，在watcher里同步滚动会滚向
#      过期目标值，表现为内容长出来了视口却停在原地，必须走延迟贴底
#   4. widget未排版时量不出高度；出窗前先删就永久坐实猜测值——widget置None后重排链断掉，
#      这条entry再没有被测量的机会。得推迟出窗并卡重试上限
#   5. 「内容不满屏时从底部往上长」是anchor()的副作用：_compositor.py的container分支用
#      set_reactive直写scroll_y、绕开validate_scroll_y的[0,max]钳位，内容不满屏时算出负值
#      把内容顶下去。所以不走anchor()就得靠CSS align-vertical: bottom补回这个观感



# channel内容区：VerticalScroll子类
class ChannelBody(VerticalScroll):
    def __init__(self,channel,body_id:str):
        super().__init__(id=body_id)
        self.channel = channel
        # 尾部置底槽，后续赋值
        self.bottom_widget = None

    # 有置底件才 yield，钉在滚动区最后
    def compose(self):
        if self.bottom_widget is not None:
            yield self.bottom_widget

    # 消息挂滚动区：有置底件就插到它前面
    def mount_content(self,widget):
        if self.bottom_widget is not None:
            self.mount(widget,before=self.bottom_widget)
            return
        self.mount(widget)

    # Textual原生贴底：锚定时内容增高跟底；用户上滚会release
    def stick_bottom(self):
        self.anchor(True)

# 事件分发注册表：event 名 → handler 方法名；@event_handler 注册，handle_event 查表分发
# 放模块级而非类内：类体里跑装饰器时还没有实例，注册表放类里要和 __init__ 的实例属性纠缠，语义易踩坑
event_methods:dict[str,str] = {}
def event_register(event:str):
    def register(method):
        event_methods[event] = method.__name__
        return method
    return register

class TuiChannel:

    # 初始化一个agent的channel
    def __init__(self,channel_id:int = None,agent_name:str = None,channel_type:str = None,channel_loop=None):
        # TuiChannel 的基本信息
        self.agent_name = agent_name
        self.channel_id = channel_id
        self.channel_loop = channel_loop
        self.channel_type = channel_type

        self.body = ChannelBody(channel=self,body_id=f"{agent_name}_CHANNEL_BODY")
        self.once_widgets:dict = {}
        self.stream_widgets:dict = {}
        self.tool_widgets:dict = {}# toolcall and toolresult use tool_id to group store

        self.loop_running = False

    # 一次性的信息，无需流式处理
    def append_once(self,content_type:str=None,content:dict=None,widget_id:str=None):
        new_widget = tuiwidgets.build_widget(widget_type=content_type,widget_content=content,widget_id=widget_id)
        self.body.mount_content(new_widget)
        self.once_widgets[widget_id] = new_widget

    # 流式信息，需要流式处理，widget_id需要传入的时候就直接拼接
    def append_stream(self,content_type:str=None,content:dict=None,widget_id:str=None):
        if widget_id not in self.stream_widgets.keys():
            new_widget = tuiwidgets.build_widget(widget_type=content_type,widget_content=content,widget_id=widget_id)
            self.body.mount_content(new_widget)
            self.stream_widgets[widget_id] = new_widget
            return
        # 每个widget内都需要有一个update_widget方法
        self.stream_widgets[widget_id].update_widget(widget_content=content)

    def handle_loop_emit(self,event:str=None,content:dict=None,stream_id:str=None,agent_name:str=None):
        if event not in event_methods.keys():
            self.append_once(content_type="SystemError",content={"message":f"未知事件: {event}"})
            return
        method_name = event_methods[event]
        if not getattr(self,method_name,None):
            self.append_once(content_type="SystemError",content={"message":f"未知事件: {event}"})
            return
        getattr(self,method_name)(content=content,agent_name=agent_name,stream_id=stream_id)

    # SystemError 一次性挂滚区
    @event_register(event="SystemError")
    def _SystemError_method(self,content:dict,**args):
        self.append_once(content_type="SystemError",content=content)

    # AssistantContent 处理方法
    @event_register(event="AssistantContent")
    def _AssistantContent_method(self,content:dict,stream_id:str,**args):
        self.append_stream(content_type="AssistantContent",widget_id=f"AssistantContent_{stream_id}",content=content)

    # AssistantThinking 处理方法 更新ThinkingWidget内容
    @event_register(event="AssistantThinking")
    def _AssistantThinking_method(self,content:dict,stream_id:str,**args):
        self.append_stream(content_type="AssistantThinking",widget_id=f"AssistantThinking_{stream_id}",content=content)

    # AssistantThinkingStreamEnd 处理方法 收尾ThinkingWidget
    @event_register(event="AssistantThinkingStreamEnd")
    def _AssistantThinkingStreamEnd_method(self,content:dict,stream_id:str,**args):
        if self.stream_widgets.get(f"AssistantThinking_{stream_id}",None):
            self.stream_widgets[f"AssistantThinking_{stream_id}"].thinking_stream_end()

    # ToolCallUpdate 处理方法：widget 未建则懒建，已建则更新（Init 事件已退役，首次 Update 即出生）
    @event_register(event="AssistantToolCallUpdate")
    def _AssistantToolCallUpdate_method(self,content:dict,**args):
        tool_widget = self.tool_widgets.get(content['tool_call_id'])
        if tool_widget:
            tool_widget.update_widget(content)
        else:
            self.append_once(content_type="AssistantToolCall",content=content,widget_id=content['tool_call_id'])
            self.tool_widgets[content['tool_call_id']] = self.once_widgets[content['tool_call_id']]

    # 一条流收尾：finalize 该流下全部 widget 并从缓存移除（同一流可挂多个 widget 类型，按 stream_id 归组）
    @event_register(event="StreamEnd")
    def end_stream(self,stream_id:str,**args):
        finished = [k for k in self.stream_widgets if k.endswith(stream_id)]
        for k in finished:
            self.stream_widgets[k].finalize()
            del self.stream_widgets[k]

    @event_register(event="LoopStart")
    def start_loop(self,**args):
        if self.body.bottom_widget is not None:
            return
        self.loop_running = True
        self.body.bottom_widget = tuiwidgets.build_widget(widget_type="BottomThinkTip",widget_content={},widget_id="BottomThinkTip")
        self.body.mount(self.body.bottom_widget)

    
    @event_register(event="LoopEnd")
    def end_loop(self,**args):
        if self.body.bottom_widget is None:
            return
        self.body.bottom_widget.finalize()
        self.body.bottom_widget = None
        self.loop_running = False
