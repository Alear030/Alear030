from ...tui_widgets import widget_register

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal,Vertical


# 注意：这些值经 Textual inline `styles.color =` setter 赋值，setter 按空白 split 后逐 token parse，
# rgb() 内带空格会被切成 'rgb(255,' 碎片报 StyleValueError，必须用无空格格式（css 文件路径不受此限）
PointerCss = {
    "waiting": "rgb(108,108,108)",
    "processing": "rgb(255,255,255)",
    "success": "rgb(0,255,94)",
    "error": "rgb(255,0,0)",
    "basic_error": "rgb(255,0,0)",
    "finished": "rgb(255,255,255)"
}



css_file = Path(__file__).parent/'widget_css.tcss'

@widget_register(widget_type="AssistantToolCall",widget_css_file=css_file,widget_enable=True)
class AssistantToolCall(Widget):
    def __init__(self,widget_content:dict,widget_id:str=None):
        super().__init__(classes='AssistantToolCall')
        self.widget_content = widget_content
        # emit 内容整包是 asdict(ToolCallResult)：状态在内层 tool_call_state dict
        self.tool_call_state = (widget_content.get("tool_call_state") or {}).get("tool_call_state") or "waiting"
        self.tool_name = widget_content.get("tool_name",None)

        self.tool_call_pointer = Static(content="●",classes=f'AssistantToolCall_tool_call_pointer')
        self.tool_call_name = Static(content=f"{self.tool_name}",classes=f'AssistantToolCall_tool_call_name')

        self.extra_body = Vertical(classes='AssistantToolCall_tool_call_extrabody')
        self.extra_body.display = False

        self.basic_errror_bar = Horizontal(classes="AssistantToolCall_basic_error_bar")
        self.basic_error_pointer = Static(content = "⎿",classes = "AssistantToolCall_basic_error_pointer")
        self.basic_error_message = Static(content="",classes=f'AssistantToolCall_basic_error_message')
        self.basic_errror_bar.display = False

        self.pointer_blinking = False
        self.pointer_blinking_target = self.tool_call_pointer

    def compose(self):
        with Horizontal(classes='AssistantToolCall_tool_call_horizontal'):
            yield self.tool_call_pointer
            yield self.tool_call_name
        # 子节点在 compose 声明式挂载，运行时只改 display/content（Textual 容器无 add_child）
        # extra_body 与标题行平级，避免缩进进 Horizontal 后错误条挤在同行
        with self.extra_body:
            with self.basic_errror_bar:
                yield self.basic_error_pointer
                yield self.basic_error_message
    
    def on_mount(self):
        # 懒建出生即带状态：复用 update_widget 应用初始态（颜色/消息/闪烁）
        self.update_widget(self.widget_content)

    def update_widget(self,widget_content:dict):
        self.widget_content = widget_content
        self.tool_name = widget_content.get("tool_name",None)
        if widget_content.get("tool_call_state",None):
            self.tool_call_state = widget_content['tool_call_state']['tool_call_state']
        
        # 处理指针颜色
        if self.tool_call_state not in ("waiting","processing","success","error","finished","basic_error"):
            return
        self.tool_call_pointer.styles.color = PointerCss[self.tool_call_state]
        
        # 处理基本错误消息：节点已随 compose 挂载，只改内容与容器显隐
        # extra_body 是父容器，只开 bar 不够（父 display=False 时子节点不可见）
        if self.tool_call_state == "basic_error":
            self.basic_error_message.update(widget_content['tool_call_state']['tool_call_state_message'])
            self.extra_body.display = True
            self.basic_errror_bar.display = True
        
        # 处理指针闪烁
        if self.tool_call_state == "processing":
            self._start_pointer_blinking()
        else:
            self._pointer_blinking_stop()
    
    # 指针闪烁
    def _start_pointer_blinking(self):
        if self.pointer_blinking:
            return
        self.pointer_blinking = True
        self._pointer_fade_out()

    # 指针闪烁淡出
    def _pointer_fade_out(self):
        if not self.pointer_blinking:
            self.pointer_blinking_target.styles.opacity = 1.0
            return
        self.pointer_blinking_target.styles.animate(
            "opacity",0.3,duration=0.75,
            easing="in_out_sine",
            on_complete=self._pointer_fade_in,
        )
    
    # 指针闪烁淡入
    def _pointer_fade_in(self):
        if not self.pointer_blinking:
            self.pointer_blinking_target.styles.opacity = 1.0
            return
        self.pointer_blinking_target.styles.animate(
            "opacity",1.0,duration=0.75,
            easing="in_out_sine",
            on_complete=self._pointer_fade_out,
        )
    
    # 指针闪烁停止
    def _pointer_blinking_stop(self):
        if not self.pointer_blinking:
            return
        self.pointer_blinking = False
        self.tool_call_pointer.styles.animate("opacity",1.0,duration=0)