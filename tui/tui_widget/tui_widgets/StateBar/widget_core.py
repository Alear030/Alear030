from ...tui_widgets_core import widget_register

from pathlib import Path

from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal

css_file = Path(__file__).parent / 'widget_css.tcss'

STATE_BAR_CONTENT_LIST = {
    "default": {"icon": "🔄Default mode on", "description": "|Other mode will release soon"}
}

@widget_register(widget_type="StateBar", widget_css_file=css_file, widget_enable=True)
class StateBar(Widget):
    def __init__(self, widget_content: dict | None = None, widget_type="StateBar", widget_id: str = None):
        super().__init__(classes='StateBar')
        self.widget_id = widget_id or "STATE_BAR"
        self.widget_content = widget_content or {}
        self.state = self.widget_content.get("state", "default")
        state_meta = STATE_BAR_CONTENT_LIST.get(self.state, STATE_BAR_CONTENT_LIST["default"])

        self.state_horizontal = Horizontal(classes="StateBar_horizontal")
        self.state_label = Static(
            state_meta["icon"] + " " + state_meta["description"],
            classes="StateBar_state_content",
        )

    def compose(self):
        with self.state_horizontal:
            yield self.state_label
