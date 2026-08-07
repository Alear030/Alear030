from ...tui_widgets import widget_register

import asyncio
from pathlib import Path
from textual import work
from textual.widget import Widget
from textual.widgets import Markdown,Static
from textual.containers import Horizontal

css_file = Path(__file__).parent/'widget_css.tcss'

@widget_register(widget_type="AssistantContent",widget_css_file=css_file,widget_enable=True)
class AssistantContent(Widget):
    # MarkdownStream串行泵：本地全文权威，finalize后update兜底
    def __init__(self,widget_content:dict=None,widget_id:str=None):
        super().__init__(classes='AssistantContent')
        self.widget_id = widget_id

        # 全文权威；frag待泵；pending兜mount前
        self.message_content = ""
        self._frag_buf:list[str] = []
        self.message_content_pending:list[str] = []
        # 泵是否已挂
        self._stream_worker = False

        # 防finalize重复收尾
        self.has_been_finalized = False

        # 首段进权威+pending；Markdown空起步，首段也走stream
        first_delta = str((widget_content or {}).get('message_delta', ''))
        if first_delta:
            self.message_content = first_delta
            self.message_content_pending.append(first_delta)

        # 指针与内容：内容空起步由泵写入，指针固定不变
        self.assistant_content_pointer = Static(content='●',classes='AssistantContent_assistant_output_pointer')
        self.assistant_content_content = Markdown(
            '',
            classes='AssistantContent_assistant_output_content',
            id=f"{self.widget_id}",
        )

    def compose(self):
        with Horizontal(classes = "AssistantContent_assistant_output_horizontal"):
            yield self.assistant_content_pointer
            yield self.assistant_content_content

    # mount：冲刷pending；已finalize直接定稿，否则开泵
    def on_mount(self):
        self._flush_pending_to_buf()
        if self.has_been_finalized:
            self._safety_update()
        elif self._frag_buf:
            self._ensure_stream_pump()

    # mount前pending并入frag缓冲
    def _flush_pending_to_buf(self):
        if self.message_content_pending:
            self._frag_buf.extend(self.message_content_pending)
            self.message_content_pending = []

    # 确保唯一@work泵在跑
    def _ensure_stream_pump(self):
        if self._stream_worker:
            return
        self._stream_worker = True
        self._stream_pump()

    # 串行泵：await write批 → finalize且缓冲空则停 → finally await stop
    @work
    async def _stream_pump(self):
        stream = Markdown.get_stream(self.assistant_content_content)
        try:
            while True:
                if self._frag_buf:
                    batch = ''.join(self._frag_buf)
                    self._frag_buf.clear()
                    if batch:
                        await stream.write(batch)
                    continue
                if self.has_been_finalized:
                    break
                await asyncio.sleep(0.05)
        finally:
            await stream.stop()
            self._stream_worker = False
            # 泵退出后定稿同步，杜绝空●
            if self.has_been_finalized:
                self.call_after_refresh(self._safety_update)

    # 用全文权威做一次Markdown.update定稿
    def _safety_update(self):
        if self.message_content:
            self.assistant_content_content.update(self.message_content)

    # 流式增量：同步权威；未mount进pending；已mount进frag并开泵
    def update_widget(self,widget_content:dict):
        delta = widget_content.get('message_delta') or ''
        # 空delta直接跳过
        if not delta:
            return
        # 同步权威，防丢字
        self.message_content += delta
        # 未mount进pending
        if not self.is_mounted:
            self.message_content_pending.append(delta)
            return
        self._frag_buf.append(delta)
        self._ensure_stream_pump()

    # 流结束：置finalize、冲刷pending，泵排空后定稿；无泵则直接定稿
    def finalize(self):
        # 防重复收尾
        if self.has_been_finalized:
            return
        self.has_been_finalized = True

        # 未mount：等on_mount定稿
        if not self.is_mounted:
            return

        self._flush_pending_to_buf()
        # 还有待泵或泵在跑：交给泵收尾；否则立刻定稿
        if self._frag_buf or self._stream_worker:
            self._ensure_stream_pump()
        else:
            self.call_after_refresh(self._safety_update)
