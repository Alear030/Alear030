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

    def append_stream(self,content_type:str,stream_id:str,content:dict):
        if stream_id not in self.stream_widgets.keys():
            new_widget = tuiwidgets.build_widget(widget_type=content_type,widget_content=content)
            self.body.mount(new_widget)
            self.stream_widgets[stream_id] = new_widget

        if content:
            self.stream_widgets[stream_id].update_widget(widget_content=content)




    