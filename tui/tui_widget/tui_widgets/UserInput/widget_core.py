from ...tui_widgets_core import widget_register

from pathlib import Path
from textual import events, on
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, TextArea
from textual.containers import Horizontal

css_file = Path(__file__).parent / 'widget_css.tcss'


@widget_register(widget_type="UserInput", widget_css_file=css_file, widget_enable=True)
class UserInput(Widget):

    class Submitted(Message):
        def __init__(self, user_input: "UserInput", value: str) -> None:
            self.user_input = user_input
            self.value = value
            super().__init__()

    # App compose 用；widget_content 仅兼容 build_widget 签名
    def __init__(self, widget_content: dict | None = None, widget_type="UserInput", widget_id: str = None):
        super().__init__(classes='UserInput')
        self.widget_id = widget_id or "USER_INPUT"
        self.placeholder = (widget_content or {}).get('placeholder', "")

        # 高度限制 & 贴底：↑ 关掉，光标回文末 / 清空再开；从第 2 行起撑高
        # border-box 下上下边框各占 1 行，styles.height 要加上这两行
        self.min_height = 1
        self.max_height = 9
        self._border_rows = 2
        self.input_core_scroll = True

    def compose(self):
        with Horizontal():
            self.pointer = Static(">", classes='UserInput_pointer')
            self.user_input_core = UserInputCore(
                id=self.widget_id,
                classes="UserInputCore",
                placeholder=self.placeholder,
                user_input=self,
            )
            yield self.pointer
            yield self.user_input_core

    def on_mount(self):
        self._sync_height()

    # 按行数撑外壳高度；贴底开启时滚到文末
    def _sync_height(self):
        core = self.user_input_core
        # 硬换行用 document.lines；长行 soft wrap 用 wrapped height
        hard = len(core.document.lines) if core.document.lines else 1
        soft = max(1, core.wrapped_document.height)
        lines = max(hard, soft)
        content_h = min(max(lines, self.min_height), self.max_height)
        # +边框行：否则 height=1 时内容被边框吃光，只剩两条线
        self.styles.height = content_h + self._border_rows
        self.refresh(layout=True)
        if self.input_core_scroll:
            core.scroll_end(animate=False)

    def _set_focus(self):
        self.user_input_core.focus()

    def _clear(self):
        self.input_core_scroll = True
        self.user_input_core.text = ""
        self._sync_height()

    def _set_disabled(self, disabled: bool):
        self.user_input_core.disabled = disabled

    # 内容变了：重算高度 / 按需贴底
    @on(TextArea.Changed)
    def _on_text_area_changed(self, event: TextArea.Changed):
        if event.text_area is not self.user_input_core:
            return
        self._sync_height()

    # 光标回到文末：恢复自动贴底
    @on(TextArea.SelectionChanged)
    def _on_selection_changed(self, event: TextArea.SelectionChanged):
        if event.text_area is not self.user_input_core:
            return
        if self._cursor_at_end(event.selection.end):
            self.input_core_scroll = True

    def _cursor_at_end(self, location) -> bool:
        row, col = location
        lines = self.user_input_core.document.lines
        if not lines:
            return True
        last = len(lines) - 1
        return row >= last and col >= len(lines[last])


class UserInputCore(TextArea):

    def __init__(self, placeholder: str = "", user_input=None, **kwargs):
        # placeholder 是 reactive，必须先 super 再碰；自己的字段放后面
        super().__init__(placeholder=placeholder or "",highlight_cursor_line=False,**kwargs)
        self._user_input = user_input
        # 隐藏滚动条；超 max 仍可用 ↑↓ 滚
        self.show_vertical_scrollbar = False
        self.show_horizontal_scrollbar = False

    # Enter 发送；Ctrl+Enter / ctrl+j 换行；↑ 关贴底
    def _on_key(self, event: events.Key):
        if event.key == "up" and self._user_input is not None:
            self._user_input.input_core_scroll = False

        if event.key in ("ctrl+j", "ctrl+enter"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            # Changed 有时布局未刷新完；换行后直接撑高
            if self._user_input is not None:
                self._user_input._sync_height()
            return

        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self._user_input.Submitted(self._user_input, self.text))
            return

        return super()._on_key(event)
