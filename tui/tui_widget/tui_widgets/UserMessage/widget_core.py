from ...tui_widgets_core import widget_register

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Static

css_file = Path(__file__).parent/"widget_css.tcss"


@widget_register(widget_type='UserMessage',widget_css_file=css_file,widget_enable=True)
class UserMessage(Widget):
    def __init__(self,widget_content:dict):
        super().__init__(classes='UserMessage')
        self.widget_content = widget_content
        self.user_input = self._get_user_input()

    def compose(self):
        yield Static(content=self.user_input,classes='UserMessage_user_input')

    def _get_user_input(self)->str:
        if self.widget_content.get('user_input'):
            return str(self.widget_content.get('user_input'))
        else:
            return 'user input has been missed'

    # 占位
    def finalize(self):
        return
