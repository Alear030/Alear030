from ...tui_widgets import widget_register

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Static
from textual.reactive import reactive
from textual.css.query import NoMatches

css_file = Path(__file__).parent/'widget_css.tcss'


@widget_register(widget_type="AssistantMessage",widget_css_file=css_file,widget_enable=True)
class AssistantMessage(Widget):
    # 流式状态：赋值自动触发 watch_message_content，compose 读它渲染
    message_content = reactive("")

    def __init__(self,widget_content:dict):
        super().__init__(classes='AssistantMessage')
        # 首段内容：build_widget 时可能已带内容，直接读
        self.message_content = str(widget_content.get('message_content', ''))

    def compose(self):
        yield Static(content=self.message_content,classes='AssistantMessage_output')

    def update_widget(self,widget_content:dict):
        # 发全量：整段替换不累积，累积在 loop 那一侧；赋值触发 watch 刷新
        if widget_content.get("message_content"):
            self.message_content = widget_content["message_content"]

    def watch_message_content(self, value: str):
        # compose 前赋值 watch 也会跑，此时内层节点还没生成；
        # 值已存 reactive，compose 读它，节点在时直接刷
        try:
            self.query_one(".AssistantMessage_output").update(value)
        except NoMatches:
            pass
