from ...tui_widgets import widget_register

import asyncio
from time import monotonic
from pathlib import Path
from textual import on, work
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal
from textual.events import Click, Mount

css_file = Path(__file__).parent/'widget_css.tcss'


@widget_register(widget_type="AssistantThinking",widget_css_file=css_file,widget_enable=True)
class AssistantThinking(Widget):
    # brief计时条 / details全文：点击互切；details走Static串行泵纯文本刷
    def __init__(self,widget_content:dict=None,widget_id:str=None):
        super().__init__(classes='AssistantThinking')
        self.widget_id = widget_id

        # 计时：mount起跑，stream_end停
        self.strt_time = monotonic()
        self.elapsed_time = 0
        self._timer = None
        self.brief_bar_display = True

        # 全文权威；frag待泵；pending兜mount前
        self.thinking_content = ""
        self._frag_buf:list[str] = []
        self.thinking_content_pending:list[str] = []
        self._stream_worker = False

        # 防stream_end / finalize重复收尾
        self.has_been_finalized = False

        # 首段进权威+pending；Static空起步，首段也走泵
        first_delta = str((widget_content or {}).get('reasoning_delta', ''))
        if first_delta:
            self.thinking_content = first_delta
            self.thinking_content_pending.append(first_delta)

        # brief条：● + Thinking计时
        self.assistant_thinking_brief_pointer = Static(content='●',classes='AssistantThinking_assistant_thinking_output_brief_pointer')
        self.assistant_thinking_brief_timer = Static(content=f'Alear030 Thinking in {self.elapsed_time:.1f}s',classes='AssistantThinking_assistant_thinking_output_brief_timer')
        self.assistant_thinking_brief_bar = Horizontal(
            self.assistant_thinking_brief_pointer,
            self.assistant_thinking_brief_timer,
            classes='AssistantThinking_assistant_thinking_output_brief_bar',
        )
        self.assistant_thinking_brief_bar.display = self.brief_bar_display

        # details条：● + thinking纯文本；默认藏
        self.assistant_thinking_details_pointer = Static(content='●',classes='AssistantThinking_assistant_thinking_output_details_pointer')
        self.assistant_thinking_details_content = Static(content='',markup=False,classes='AssistantThinking_assistant_thinking_output_details_content')
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

    # mount：开计时；冲pending；已finalize定稿，否则开泵
    @on(Mount)
    def _on_mount(self):
        self._timer = self.set_interval(1.0,self._refresh_timer)
        self._refresh_timer()
        self._flush_pending_to_buf()
        if self.has_been_finalized:
            self.assistant_thinking_brief_timer.update(f'Alear030 Done Thinking in {self.elapsed_time:.1f}s')
            self._safety_update()
            if self._timer:
                self._timer.stop()
                self._timer = None
        else:
            if self._frag_buf:
                self._ensure_stream_pump()
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

    # mount前pending并入frag缓冲
    def _flush_pending_to_buf(self):
        if self.thinking_content_pending:
            self._frag_buf.extend(self.thinking_content_pending)
            self.thinking_content_pending = []

    # 确保唯一@work泵在跑
    def _ensure_stream_pump(self):
        if self._stream_worker:
            return
        self._stream_worker = True
        self._stream_pump()

    # 串行泵：有frag就用权威全文刷Static → finalize且缓冲空则停
    @work
    async def _stream_pump(self):
        try:
            while True:
                if self._frag_buf:
                    self._frag_buf.clear()
                    if self.thinking_content:
                        self.assistant_thinking_details_content.update(self.thinking_content.rstrip('\n'))
                    continue
                if self.has_been_finalized:
                    break
                await asyncio.sleep(0.05)
        finally:
            self._stream_worker = False
            if self.has_been_finalized:
                self.call_after_refresh(self._safety_update)

    # 用全文权威做一次Static.update定稿
    def _safety_update(self):
        if self.thinking_content:
            self.assistant_thinking_details_content.update(self.thinking_content.rstrip('\n'))

    # 流式增量：同步权威；未mount进pending；已mount进frag并开泵
    def update_widget(self,widget_content:dict):
        delta = widget_content.get('reasoning_delta') or ''
        if not delta:
            return
        self.thinking_content += delta
        if not self.is_mounted:
            self.thinking_content_pending.append(delta)
            return
        self._frag_buf.append(delta)
        self._ensure_stream_pump()

    # 流结束：改Done文案、停计时；泵排空后定稿
    def thinking_stream_end(self):
        if self.has_been_finalized:
            return
        self.has_been_finalized = True
        self._pointer_blinking_stop()

        self.elapsed_time = monotonic() - self.strt_time
        if self._timer:
            self._timer.stop()
            self._timer = None

        if not self.is_mounted:
            return

        self.assistant_thinking_brief_timer.update(f'Alear030 Done Thinking in {self.elapsed_time:.1f}s')
        self._flush_pending_to_buf()
        if self._frag_buf or self._stream_worker:
            self._ensure_stream_pump()
        else:
            self.call_after_refresh(self._safety_update)

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
