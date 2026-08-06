from ...tui_widgets import widget_register

from pathlib import Path
from textual import on
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal,Vertical
from textual.reactive import reactive

css_file = Path(__file__).parent/'widget_css.tcss'

@widget_register(widget_type="AssistantToolCall",widget_css_file=css_file,widget_enable=True)
class AssistantToolCall(Widget):
    def __init__(self,widget_content:dict,widget_id:str=None):
        super().__init__(classes='AssistantToolCall')
        self.tool_call_state = widget_content.get("tool_call_state",None) or "waiting"

        self.tool_cal_pointer = Static(content="●",classes=f'AssistantToolCall_tool_call_pointer_{self.tool_call_state}')
        self.tool_call_name = Static(content=f"{self.widget_content['tool_name']}...",classes=f'AssistantToolCall_tool_call_name_{self.tool_call_state}')
        self.tool_call_basic_error_message = Static(content="",classes=f'AssistantToolCall_tool_call_basic_error_message')
        self.tool_call_basic_error_message.display = True

    def compose(self):
        with Horizontal(classes='AssistantToolCall_tool_call_horizontal'):
            yield self.tool_call_pointer
            with Vertical(classes='AssistantToolCall_tool_call_vertical'):
                yield self.tool_call_name
                yield self.tool_call_basic_error_message
    
    def update_widget(self,widget_content:dict):
        new_tool_call_state = widget_content.get("tool_call_state",None)
        if new_tool_call_state == "basic_error":
            new_tool_call_state = "error"
            self.tool_cal_pointer.remove_class(f"AssistantToolCall_tool_call_pointer_{self.tool_call_state}")
            self.tool_cal_pointer.add_class(f"AssistantToolCall_tool_call_pointer_{new_tool_call_state}")
            self.tool_call_name.update(content=f"{self.widget_content['tool_name']}")
            self.tool_call_basic_error_message.content = f"{self.widget_content['error_message']}"
            self.tool_call_basic_error_message.display = True
            return

        if self.tool_call_state != new_tool_call_state:
            self.tool_call_pointer.remove_class(f"AssistantToolCall_tool_call_pointer_{self.tool_call_state}")
            self.tool_call_pointer.add_class(f"AssistantToolCall_tool_call_pointer_{new_tool_call_state}")
            self.tool_call_name.content = f"{self.widget_content['tool_name']}"