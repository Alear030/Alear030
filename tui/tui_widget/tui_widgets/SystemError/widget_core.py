from ...tui_widgets_core import widget_register

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal

css_file = Path(__file__).parent/"widget_css.tcss"


@widget_register(widget_type='SystemError',widget_css_file=css_file,widget_enable=True)
class SystemError(Widget):
    def __init__(self,widget_content:dict,widget_id:str=None):
        super().__init__(classes='SystemError')
        self.widget_content = widget_content or {}
        self.widget_id = widget_id
        self.error_message = self._get_error_message()

        self.error_pointer = Static(content='!',classes='SystemError_pointer')
        self.error_content = Static(content=self.error_message,markup=False,classes='SystemError_content')

    def compose(self):
        with Horizontal(classes="SystemError_horizontal"):
            yield self.error_pointer
            yield self.error_content

    def _get_error_message(self)->str:
        if self.widget_content.get('message'):
            return str(self.widget_content.get('message'))
        else:
            return 'system error has been missed'

    # 占位
    def finalize(self):
        return
