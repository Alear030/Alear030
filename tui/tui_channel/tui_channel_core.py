from ..tui_widget import tuiwidgets


from contextlib import _AsyncGeneratorContextManager
from dataclasses import dataclass
from textual.containers import VerticalScroll,Horizontal
from textual.widgets import Static


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
        self.body = VerticalScroll(id=f"{agent_name}_CONTENT_AREA")

        self.once_widgets:dict = {}
        self.stream_widgets:dict = {}
        self.tool_widgets:dict = {}# toolcall and toolresult use tool_id to group store

    # 一次性的信息，无需流式处理
    def append_once(self,content_type:str,content:dict,stream_id:str):
        new_widget = tuiwidgets.build_widget(widget_type=content_type,widget_content=content,widget_id=f"{content_type}_{stream_id}")
        self.body.mount(new_widget)
        self.once_widgets[f"{content_type}_{stream_id}"] = new_widget

    def append_stream(self,content_type:str,stream_id:str,content:dict):
        widget_id = f"{content_type}_{stream_id}"
        if widget_id not in self.stream_widgets.keys():
            # 首建：首包交给 widget 构造，首段 delta 在 __init__ 落进 Markdown 初始内容
            new_widget = tuiwidgets.build_widget(widget_type=content_type,widget_content=content,widget_id=widget_id)
            self.body.mount(new_widget)
            self.stream_widgets[widget_id] = new_widget
            return

        # 后续增量包：widget 内部转发给 MarkdownStream
        self.stream_widgets[widget_id].update_widget(widget_content=content)

    def handle_loop_emit(self,event:str,content:dict,stream_id:str,agent_name:str):
        if event not in event_methods.keys():
            return # @claude 后续增加System_error widget承接
        method_name = event_methods[event]
        if not getattr(self,method_name,None):
            return # @claude 后续增加System_error widget承接
        getattr(self,method_name)(content=content,agent_name=agent_name,stream_id=stream_id)

    # AssistantContent 处理方法
    @event_register(event="AssistantContent")
    def _AssistantContent_method(self,content:dict,stream_id:str,**args):
        self.append_stream(content_type="AssistantMessage",stream_id=stream_id,content=content)

    # AssistantThinking 处理方法
    @event_register(event="AssistantThinking")
    def _AssistantThinking_method(self,content:dict,stream_id:str,**args):
        self.append_stream(content_type="AssistantThinking",stream_id=stream_id,content=content)

    # 一条流收尾：finalize 该流下全部 widget 并从缓存移除（同一流可挂多个 widget 类型，按 stream_id 归组）
    @event_register(event="StreamEnd")
    def end_stream(self,stream_id:str,**args):
        finished = [k for k in self.stream_widgets if k.endswith(stream_id)]
        for k in finished:
            self.stream_widgets[k].finalize()
            del self.stream_widgets[k]

        # @claude 后续增加toolcall toolresult




    