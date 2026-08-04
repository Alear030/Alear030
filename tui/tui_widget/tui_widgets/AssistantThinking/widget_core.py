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
        self.reasoning_content = widget_content.get('reasoning_delta','')

    def compose(self):
        yield Static(self.reasoning_content,classes='AssistantThinking_output',id=self.widget_id)

    def update_widget(self,widget_content:dict):
        self.reasoning_content = self.reasoning_content + widget_content.get('reasoning_delta','')
        self.query_one(f"#{self.widget_id}").update(self.reasoning_content)

    def finalize(self):
        return