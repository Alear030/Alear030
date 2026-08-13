from ..AskUserQuestion import AskUserQuestion

from textual import widget
from ...tui_widgets_core import widget_register
from ..UserInput.widget_core import UserInput
from ..StateBar.widget_core import StateBar

from pathlib import Path

from textual.widget import Widget
from textual.containers import Vertical

css_file = Path(__file__).parent / 'widget_css.tcss'

event_methods:dict[str,str] = {}
def event_register(event:str):
    def register(method):
        event_methods[event] = method.__name__
        return method
    return register

@widget_register(widget_type="BottomBar", widget_css_file=css_file, widget_enable=True)
class BottomBar(Widget):
    def __init__(self, widget_content: dict | None = None, widget_type="BottomBar", widget_id: str = None):
        super().__init__(classes='BottomBar')
        self.widget_id = widget_id or "BOTTOM_BAR"
        self.widget_content = widget_content or {}

        # 整体bottom外部容器
        self.bottom_bar_vertical = Vertical(classes = "BottomBar_vertical")

        # default默认用户输入和状态展示等容器
        self.default_vertical = Vertical(classes = "BottomBar_default_vertical")
        self.user_input = UserInput(widget_content=self.widget_content, widget_type="UserInput", widget_id="USER_INPUT")
        self.state_bar = StateBar(widget_content=self.widget_content, widget_type="StateBar", widget_id="STATE_BAR")

        # AskUserQuestion 槽：未挂起为 None，提交后 event_stop 清掉
        self.askuserquestion = None

        self.event_methods = event_methods
        

    def compose(self):
        with self.bottom_bar_vertical:
            with self.default_vertical:
                yield self.user_input
                yield self.state_bar

    # UserInput相关方法
    def UserInput_set_focus(self):
        if self.user_input.display and not self.user_input.disabled:
            self.user_input._set_focus()

    def UserInput_clear(self):
        self.user_input._clear()

    def UserInput_set_disabled(self, disabled: bool):
        self.user_input._set_disabled(disabled)
    
    # Click/Mount 把焦点拉回底部：Ask 挂起时不抢回 UserInput
    def always_on_focus(self):
        if self.askuserquestion is not None:
            # 落到自行输入行才有这个 Input；否则焦在 Ask 上接↑↓
            ask_input = self.askuserquestion.askquestion_user_input
            if ask_input is not None:
                # 已在 Input 上再 focus 会整段全选，跳过
                if self.app.focused is not ask_input:
                    ask_input.focus()
                return
            if self.app.focused is not self.askuserquestion:
                self.askuserquestion.focus()
            return
        if self.user_input.display and not self.user_input.disabled:
            self.user_input._set_focus()

    # AskUserQuestion相关方法
    @event_register(event="AskUserQuestion")
    def ask_user_question_event_method(self,content:dict,**args):
        if content is None:
            return
        if self.askuserquestion is not None:
            return

        self.askuserquestion = AskUserQuestion(widget_content=content, widget_type="AskUserQuestion", widget_id="ASK_USER_QUESTION", event_stop=self.event_stop)
        self.default_vertical.display = False
        self.bottom_bar_vertical.mount(self.askuserquestion)
        self.askuserquestion.focus()

    
    def event_stop(self,event_type:str,event_widget:Widget):
        event_widget.remove()
        if event_type == "AskUserQuestion":
            self.askuserquestion = None
        self.default_vertical.display = True
        self.UserInput_set_focus()