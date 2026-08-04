from ...tui_widgets import widget_register

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Markdown

css_file = Path(__file__).parent/'widget_css.tcss'


@widget_register(widget_type="AssistantMessage",widget_css_file=css_file,widget_enable=True)
class AssistantMessage(Widget):
    # 流式渲染：首段 delta 进 Markdown 初始内容，后续增量走 MarkdownStream 累积
    def __init__(self,widget_content:dict,widget_type="AssistantMessage",widget_id:str=None):
        super().__init__(classes='AssistantMessage')
        # 首段内容：channel 首建时把首包交给构造，读新键名 message_delta
        self._first_delta = str((widget_content or {}).get('message_delta', ''))
        # 流式句柄：首段后的增量经它写入，end 时 stop
        self._stream = None

        # 每一个widget的标准信息
        self.widget_id = f"{widget_type}_{widget_id}"

    def compose(self):
        yield Markdown(self._first_delta,classes='AssistantMessage_output',id=f"{self.widget_id}")

    def update_widget(self,widget_content:dict):
        # 增量 delta：先建 stream 再异步写入；update_widget 经 call_from_thread 在 UI 线程跑，get_stream 可安全 start
        delta = widget_content.get('message_delta') or ''
        if not delta:
            return
        if self._stream is None:
            self._stream = Markdown.get_stream(self.query_one('.AssistantMessage_output'))
        # write 是 async，同步方法里用 run_worker 丢进 UI 事件循环
        self.run_worker(self._stream.write(delta))

    def finalize(self):
        # 流结束：stop 内部任务（顺带冲刷残留 pending），清句柄
        if self._stream is not None:
            self.run_worker(self._stream.stop())
            self._stream = None
