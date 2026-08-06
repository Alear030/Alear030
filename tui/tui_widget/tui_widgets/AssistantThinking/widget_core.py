from ...tui_widgets import widget_register

from time import monotonic
from pathlib import Path
from textual import on
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal
from textual.events import Click, Mount

css_file = Path(__file__).parent/'widget_css.tcss'


@widget_register(widget_type="AssistantThinking",widget_css_file=css_file,widget_enable=True)
class AssistantThinking(Widget):
    def __init__(self,widget_content:dict=None,widget_id:str=None):
        super().__init__(classes='AssistantThinking')
        self.widget_id = widget_id

        self.strt_time = monotonic()
        self.elapsed_time = 0
        self._timer = None
        self.brief_bar_display = True

        self.thinking_content = ""
        self.thinking_content_holder = ""
        self.thinking_content_holder_timer = None
        self.thinking_content_pending:list[str] = []

        self.has_been_finalized = False
        
        self.assistant_thinking_brief_pointer = Static(content='●',classes='AssistantThinking_assistant_thinking_output_brief_pointer')
        self.assistant_thinking_brief_timer = Static(content=f'Alear030 Thinking in {self.elapsed_time:.1f}s',classes='AssistantThinking_assistant_thinking_output_brief_timer')
        self.assistant_thinking_brief_bar = Horizontal(
            self.assistant_thinking_brief_pointer,
            self.assistant_thinking_brief_timer,
            classes='AssistantThinking_assistant_thinking_output_brief_bar',
        )
        self.assistant_thinking_brief_bar.display = self.brief_bar_display

        self.assistant_thinking_details_pointer = Static(content='●',classes='AssistantThinking_assistant_thinking_output_details_pointer')
        self.assistant_thinking_details_content = Static(content='',classes='AssistantThinking_assistant_thinking_output_details_content')
        self.assistant_thinking_details_bar = Horizontal(
            self.assistant_thinking_details_pointer,
            self.assistant_thinking_details_content,
            classes='AssistantThinking_assistant_thinking_output_details_bar',
        )
        self.assistant_thinking_details_bar.display = not self.brief_bar_display

    def compose(self):
        yield self.assistant_thinking_brief_bar
        yield self.assistant_thinking_details_bar

    @on(Mount)
    def _on_mount(self):
        self._timer = self.set_interval(1.0,self._refresh_timer)
        self._refresh_timer()
        if self.has_been_finalized:
            # Stream已经结束，做一次终结补偿，确保brief timer和details content都显示完整
            self.assistant_thinking_brief_timer.update(f'Alear030 Done Thinking in {self.elapsed_time:.1f}s')
            self._flush_thinking_pending()
            self._thinking_content_holder_handle()
            if self._timer:
                self._timer.stop()
                self._timer = None
        else:
            # Stream还在进行中，将mount之前的pending内容一次性刷新
            self._flush_thinking_pending()

    @on(Click)
    def _on_click(self):
        if self.thinking_content:
            self.brief_bar_display = not self.brief_bar_display
            self.assistant_thinking_brief_bar.display = self.brief_bar_display
            self.assistant_thinking_details_bar.display = not self.brief_bar_display

    def _refresh_timer(self):
        self.elapsed_time = monotonic() - self.strt_time
        self.assistant_thinking_brief_timer.update(f'Alear030 Thinking in {self.elapsed_time:.1f}s')
    
    def _flush_thinking_pending(self):
        if self.thinking_content_pending:
            for pending in self.thinking_content_pending:
                self.thinking_content_holder += pending
            self.thinking_content_pending = []
            self._thinking_content_holder_handle()

    def _thinking_content_holder_handle(self):
        if self.thinking_content_holder:
            self.thinking_content = self.thinking_content + self.thinking_content_holder
            self.thinking_content_holder = ""
            self.assistant_thinking_details_content.update(self.thinking_content.rstrip('\n'))
            self.thinking_content_holder_timer = None

    def update_widget(self,widget_content:dict):
        delta = widget_content.get('reasoning_delta','')
        if not delta:
            return
        if not self.is_mounted:
            self.thinking_content_pending.append(delta)
            return
        self.thinking_content_holder += delta
        if self.thinking_content_holder_timer is None:
            self.thinking_content_holder_timer = self.set_timer(0.5,self._thinking_content_holder_handle)

    def thinking_stream_end(self):
        if self.has_been_finalized:
            return
        self.has_been_finalized = True
        
        self.elapsed_time = monotonic() - self.strt_time
        if self.is_mounted:
            self.assistant_thinking_brief_timer.update(f'Alear030 Done Thinking in {self.elapsed_time:.1f}s')
            self._flush_thinking_pending()
            self._thinking_content_holder_handle()
        
        if self._timer:
            self._timer.stop()
            self._timer = None
        
        if self.thinking_content_holder_timer:
            self.thinking_content_holder_timer.stop()
            self.thinking_content_holder_timer = None


    def finalize(self):
        self.thinking_stream_end()