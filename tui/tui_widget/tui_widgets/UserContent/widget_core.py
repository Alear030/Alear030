from ...tui_widgets_core import widget_register

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal

css_file = Path(__file__).parent/"widget_css.tcss"


@widget_register(widget_type='UserContent',widget_css_file=css_file,widget_enable=True)
class UserContent(Widget):
    def __init__(self,widget_content:dict,widget_id:str=None):
        super().__init__(classes='UserContent')
        self.widget_content = widget_content
        self.user_input = self._get_user_input()
        self.widget_id = widget_id

        self.user_input_pointer = Static(content='●',classes='UserContent_user_input_pointer')
        self.user_input_content = Static(content=self.user_input,classes='UserContent_user_input_content')

    def compose(self):
        with Horizontal(classes = "UserContent_user_input_horizontal"):
            yield self.user_input_pointer
            yield self.user_input_content

    def _get_user_input(self)->str:
        if self.widget_content.get('user_input'):
            return str(self.widget_content.get('user_input'))
        else:
            return 'user input has been missed'

    # 占位
    def finalize(self):
        return
