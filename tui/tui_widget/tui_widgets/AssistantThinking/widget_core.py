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
    # brief计时条 / details全文：点击互切；流式delta先攒holder再定时刷
    def __init__(self,widget_content:dict=None,widget_id:str=None):
        super().__init__(classes='AssistantThinking')
        self.widget_id = widget_id

        # 计时：mount起跑，stream_end停
        self.strt_time = monotonic()
        self.elapsed_time = 0
        self._timer = None
        self.brief_bar_display = True

        # 全文缓存；holder攒增量，0.5s定时合入；pending兜mount前delta
        self.thinking_content = ""
        self.thinking_content_holder = ""
        self.thinking_content_holder_timer = None
        self.thinking_content_pending:list[str] = []

        # 防stream_end / finalize重复收尾
        self.has_been_finalized = False
        
        # brief条：● + Thinking计时
        self.assistant_thinking_brief_pointer = Static(content='●',classes='AssistantThinking_assistant_thinking_output_brief_pointer')
        self.assistant_thinking_brief_timer = Static(content=f'Alear030 Thinking in {self.elapsed_time:.1f}s',classes='AssistantThinking_assistant_thinking_output_brief_timer')
        self.assistant_thinking_brief_bar = Horizontal(
            self.assistant_thinking_brief_pointer,
            self.assistant_thinking_brief_timer,
            classes='AssistantThinking_assistant_thinking_output_brief_bar',
        )
        self.assistant_thinking_brief_bar.display = self.brief_bar_display

        # details条：● + thinking全文；默认藏
        self.assistant_thinking_details_pointer = Static(content='●',classes='AssistantThinking_assistant_thinking_output_details_pointer')
        self.assistant_thinking_details_content = Static(content='',classes='AssistantThinking_assistant_thinking_output_details_content')
        self.assistant_thinking_details_bar = Horizontal(
            self.assistant_thinking_details_pointer,
            self.assistant_thinking_details_content,
            classes='AssistantThinking_assistant_thinking_output_details_bar',
        )
        self.assistant_thinking_details_bar.display = not self.brief_bar_display

        # thinking pointer 呼吸效果
        self.pointer_blinking = False
        self.pointer_blinking_target = self.assistant_thinking_brief_pointer

    def compose(self):
        yield self.assistant_thinking_brief_bar
        yield self.assistant_thinking_details_bar

    # mount：开计时；若已finalize做终结补偿，否则冲刷pending
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
            self._start_pointer_blinking()

    # 有全文才允许点：brief ↔ details
    @on(Click)
    def _on_click(self):
        if self.thinking_content:
            self.brief_bar_display = not self.brief_bar_display
            self.assistant_thinking_brief_bar.display = self.brief_bar_display
            self.assistant_thinking_details_bar.display = not self.brief_bar_display

            self.assistant_thinking_brief_pointer.styles.opacity = 1.0
            self.assistant_thinking_details_pointer.styles.opacity = 1.0
            self.pointer_blinking_target = (
                self.assistant_thinking_brief_pointer
                if self.brief_bar_display
                else self.assistant_thinking_details_pointer
            )

    # 刷brief计时文案
    def _refresh_timer(self):
        self.elapsed_time = monotonic() - self.strt_time
        self.assistant_thinking_brief_timer.update(f'Alear030 Thinking in {self.elapsed_time:.1f}s')
    
    # pending合入holder再刷details
    def _flush_thinking_pending(self):
        if self.thinking_content_pending:
            for pending in self.thinking_content_pending:
                self.thinking_content_holder += pending
            self.thinking_content_pending = []
            self._thinking_content_holder_handle()

    # holder合入全文并update details Static
    def _thinking_content_holder_handle(self):
        if self.thinking_content_holder:
            self.thinking_content = self.thinking_content + self.thinking_content_holder
            self.thinking_content_holder = ""
            self.assistant_thinking_details_content.update(self.thinking_content.rstrip('\n'))
            self.thinking_content_holder_timer = None

    # 流式增量：未mount进pending；已mount攒holder，0.5s定时合入
    def update_widget(self,widget_content:dict):
        delta = widget_content.get('reasoning_delta','')

        if not delta:
            return
        if not self.is_mounted:
            self.thinking_content_pending.append(delta)
            return

        self.thinking_content_holder += delta
        if not self.thinking_content:
            self._thinking_content_holder_handle()
            return

        if self.thinking_content_holder_timer is None:
            self.thinking_content_holder_timer = self.set_timer(0.25,self._thinking_content_holder_handle)

    # 流结束：改Done文案、冲刷pending/holder、停计时和holder定时器
    def thinking_stream_end(self):
        if self.has_been_finalized:
            return
        self.has_been_finalized = True
        self._pointer_blinking_stop()
        
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
        


    # channel StreamEnd收口：转thinking_stream_end
    def finalize(self):
        self._pointer_blinking_stop()
        self.thinking_stream_end()
        

    
    # 效果方法
    def _start_pointer_blinking(self):
        if self.pointer_blinking:
            return
        self.pointer_blinking = True
        self._pointer_fade_out()

    def _pointer_fade_out(self):
        if not self.pointer_blinking:
            self.pointer_blinking_target.styles.opacity = 1.0
            return
        self.pointer_blinking_target.styles.animate(
            "opacity",0.3,duration=0.75,
            easing="in_out_sine",
            on_complete=self._pointer_fade_in,
        )

    def _pointer_fade_in(self):
        if not self.pointer_blinking:
            self.pointer_blinking_target.styles.opacity = 1.0
            return
        self.pointer_blinking_target.styles.animate(
            "opacity",1.0,duration=0.75,
            easing="in_out_sine",
            on_complete=self._pointer_fade_out,
        )

    def _pointer_blinking_stop(self):
        if not self.pointer_blinking:
            return
        self.pointer_blinking = False
        self.assistant_thinking_brief_pointer.styles.animate("opacity",1.0,duration=0)
        self.assistant_thinking_details_pointer.styles.animate("opacity",1.0,duration=0)
