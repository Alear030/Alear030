from ...tui_widgets import widget_register

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Markdown

css_file = Path(__file__).parent/'widget_css.tcss'


@widget_register(widget_type="AssistantContent",widget_css_file=css_file,widget_enable=True)
class AssistantContent(Widget):
    # 流式渲染：首段进Markdown，后续走MarkdownStream
    def __init__(self,widget_content:dict,widget_type="AssistantContent",widget_id:str=None):
        super().__init__(classes='AssistantContent')
        # 首段delta：channel首建时塞进构造
        self._first_delta = str((widget_content or {}).get('message_delta', ''))
        # MarkdownStream句柄，end时stop
        self._stream = None
        self.widget_id = widget_id
        # Markdown句柄提前建：防compose未完成就update
        self.content_markdown = Markdown(self._first_delta,classes='AssistantContent_output',id=f"{self.widget_id}")
        # mount前增量缓冲，on_mount再写入stream
        self._pending:list[str] = []

    def compose(self):
        yield self.content_markdown

    # mount完成：冲刷pending
    def on_mount(self):
        self._flush_pending()

    # 流式增量：未mount进pending，已mount写stream
    def update_widget(self,widget_content:dict):
        delta = widget_content.get('message_delta') or ''
        if not delta:
            return
        if not self.is_mounted:
            self._pending.append(delta)
            return
        self._write_delta(delta)

    # 单段delta写入MarkdownStream
    def _write_delta(self,delta:str):
        if self._stream is None:
            self._stream = Markdown.get_stream(self.content_markdown)
        # write是async，run_worker丢进UI循环
        self.run_worker(self._stream.write(delta))

    # pending按序写入stream
    def _flush_pending(self):
        if not self._pending:
            return
        pending = self._pending
        self._pending = []
        for delta in pending:
            self._write_delta(delta)

    # 流结束：先冲刷pending，再stop stream
    def finalize(self):
        if self._pending:
            self._flush_pending()
        if self._stream is not None:
            self.run_worker(self._stream.stop())
            self._stream = None
