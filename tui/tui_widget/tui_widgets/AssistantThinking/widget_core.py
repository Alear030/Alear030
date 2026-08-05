from ...tui_widgets import widget_register

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Static

css_file = Path(__file__).parent/'widget_css.tcss'


@widget_register(widget_type="AssistantThinking",widget_css_file=css_file,widget_enable=True)
class AssistantThinking(Widget):
    def __init__(self,widget_content:dict,widget_type="AssistantThinking",widget_id:str=None):
        super().__init__(classes='AssistantThinking')
        self.widget_id = widget_id
        self.reasoning_content = widget_content.get('reasoning_delta','') or ''
        # Static句柄提前建：防compose未完成就update；展示去掉首尾换行，避免盒内顶/底空行
        self.thinking_static = Static(self._display_text(),classes='AssistantThinking_output',id=self.widget_id)
        # mount前增量缓冲，on_mount再刷屏
        self._pending:list[str] = []

    def _display_text(self) -> str:
        # 只剥首尾换行，保留段中空白
        return (self.reasoning_content or '').lstrip('\n').rstrip('\n')

    def compose(self):
        yield self.thinking_static

    # mount完成：冲刷pending
    def on_mount(self):
        self._flush_pending()

    # 流式增量：未mount进pending，已mount直接update
    def update_widget(self,widget_content:dict):
        delta = widget_content.get('reasoning_delta','')
        if not delta:
            return
        self.reasoning_content = self.reasoning_content + delta
        if not self.is_mounted:
            self._pending.append(delta)
            return
        self.thinking_static.update(self._display_text())

    # pending刷进Static：内存串已累加，刷一次全文
    def _flush_pending(self):
        if not self._pending:
            return
        self._pending.clear()
        self.thinking_static.update(self._display_text())

    # 流结束兜底冲刷
    def finalize(self):
        if self._pending:
            self._flush_pending()
        else:
            self.thinking_static.update(self._display_text())
