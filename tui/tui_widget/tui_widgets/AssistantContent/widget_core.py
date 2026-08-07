from ...tui_widgets import widget_register

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Markdown,Static
from textual.containers import Horizontal

css_file = Path(__file__).parent/'widget_css.tcss'

@widget_register(widget_type="AssistantContent",widget_css_file=css_file,widget_enable=True)
class AssistantContent(Widget):
    # 攒字刷新：pending/holder/timer，合入后 Markdown.update 全文
    def __init__(self,widget_content:dict=None,widget_id:str=None):
        super().__init__(classes='AssistantContent')
        self.widget_id = widget_id

        # 全文缓存；holder攒增量，0.25s定时合入；pending兜mount前delta
        self.message_content = ""
        self.message_content_holder = ""
        self.message_content_pending:list[str] = []
        self.holder_timer = None

        # 防finalize重复收尾
        self.has_been_finalized = False

        # 首段delta：构造时直接进全文，Markdown带首段
        first_delta = str((widget_content or {}).get('message_delta', ''))
        if first_delta:
            self.message_content = first_delta
        
        # 指针与内容：内容节点随全文缓存，指针固定不变
        self.assistant_content_pointer = Static(content='●',classes='AssistantContent_assistant_output_pointer')
        self.assistant_content_content = Markdown(
            self.message_content if self.message_content else '',
            classes='AssistantContent_assistant_output_content',
            id=f"{self.widget_id}",
        )

    def compose(self):
        with Horizontal(classes = "AssistantContent_assistant_output_horizontal"):
            yield self.assistant_content_pointer
            yield self.assistant_content_content

    # mount：若已finalize做终结补偿，否则冲刷pending
    def on_mount(self):
        if self.has_been_finalized:
            self._flush_pending()
            self._holder_handle()
        else:
            self._flush_pending()
    
    # mount之前将pending一次性刷入holder再Markdown.update
    def _flush_pending(self):
        if self.message_content_pending:
            for pending in self.message_content_pending:
                self.message_content_holder += pending
            self.message_content_pending = []
            self._holder_handle()
        
    # holder合入全文并 Markdown.update
    def _holder_handle(self):
        if self.message_content_holder:
            self.message_content = self.message_content + self.message_content_holder
            self.message_content_holder = ""
            self.assistant_content_content.update(self.message_content)
            self.holder_timer = None

    # 流式增量：未mount进pending；已mount攒holder，首包立刻flush，其后0.25s合批
    def update_widget(self,widget_content:dict):
        delta = widget_content.get('message_delta') or ''
        # 空delta直接跳过
        if not delta:
            return
        # 未mount进pending：攒pending
        if not self.is_mounted:
            self.message_content_pending.append(delta)
            return
        # 已mount攒holder：holder累积，0.25s定时合入
        self.message_content_holder += delta
        if not self.message_content:
            self._holder_handle()
            return
        # 0.25s定时合入holder
        if self.holder_timer is None:
            self.holder_timer = self.set_timer(0.1,self._holder_handle)
        
    # 流结束：冲刷pending/holder，停timer
    def finalize(self):
        # 防重复收尾
        if self.has_been_finalized:
            return
        self.has_been_finalized = True

        # 已mount：冲刷pending/holder
        if self.is_mounted:
            self._flush_pending()
            self._holder_handle()

        # 停holder定时器
        if self.holder_timer:
            self.holder_timer.stop()
            self.holder_timer = None