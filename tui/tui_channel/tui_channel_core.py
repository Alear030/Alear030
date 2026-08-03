from ..tui_widget import tuiwidgets


from contextlib import _AsyncGeneratorContextManager
from dataclasses import dataclass
from textual.containers import VerticalScroll,Horizontal
from textual.widgets import Static


class TuiChannel:

    # 初始化一个agent的channel
    def __init__(self,channel_id:int = None,agent_name:str = None,channel_type:str = None,channel_loop=None):
        # TuiChannel 的基本信息
        self.agent_name = agent_name
        self.channel_id = channel_id
        self.channel_loop = channel_loop
        self.channel_type = channel_type
        self.body = VerticalScroll(id=f"{agent_name}_CONTENT_AREA")

        self.stream_widgets:dict = {}

    # 一次性的信息，无需流式处理
    def append_once(self,type:str,content:dict):
        new_widget = tuiwidgets.build_widget(widget_type=type,widget_content=content)
        self.body.mount(new_widget)

    # @claude 记录：后续通过content_type（widget_type）和stream_id创建widget并赋值对应的id
    # 然后每一次append_stream的时候，判断是否已经存在于本轮的已创建widget，然后分流是新建还是更新
    # 这里就需要loop侧调用emit的时候传入的type和stream_id能够对创建出来的widget进行唯一的标识
    # 同时tool_call一轮多个，stream_id是相同的，toolcall的widget后续新增的话，其实也是相同的，所以需要想一种新的标记widget的字段方式
    # 突然想到一种方式，双端维护，loop中维护一个已创建的列表，唯一id，然后同时传入，关键实际上还是怎么确定唯一标识，而且必须还得使用已有的字段进行拼接
    def append_stream(self,content_type:str,stream_id:str,content:dict):
        # 流结束信号：收尾 widget（内部 stop MarkdownStream）并从缓存移除，end 包不走 update
        if content_type == 'AssistantMessageEnd':
            widget = self.stream_widgets.pop(stream_id, None)
            if widget is not None:
                widget.finalize_stream()
            return

        if stream_id not in self.stream_widgets.keys():
            # 首建：首包交给 widget 构造，首段 delta 在 __init__ 落进 Markdown 初始内容
            new_widget = tuiwidgets.build_widget(widget_type=content_type,widget_content=content)
            self.body.mount(new_widget)
            self.stream_widgets[stream_id] = new_widget
            return

        # 后续增量包：widget 内部转发给 MarkdownStream
        self.stream_widgets[stream_id].update_widget(widget_content=content)




    