from ...tui_widgets import widget_register

import asyncio
from time import monotonic
from pathlib import Path
from textual import on, work
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal,Vertical
from textual.events import Click, Mount
import random


css_file = Path(__file__).parent/'widget_css.tcss'

# 每5秒换一句
CHANGE_INTERVAL = 5

# 底栏口吻，不说 thinking
THINING_BAR_MESSAGES = [
    "Default mode on",
    "Other modes will release soon",
    "Alear030 may run away... well just a joke lol",
    "Alear030 is doing something important..."
]

# 思考提示语
THINKING_BAR_TIPS = [
    "Alear030 only has default mode, and other modes will release soon",
    "Alear030 can remember ur information, and it can help Alear030 do better work"
]


@widget_register(widget_type="BottomThinkTip",widget_css_file=css_file,widget_enable=True)
class BottomThinkTip(Widget):
    def __init__(self,widget_content:dict=None,widget_id:str=None):
        super().__init__(classes='BottomThinkTip')
        self.widget_id = widget_id

        self.start_time = monotonic()
        self.elapsed_time = 0
        self._timer = None
        # 已轮换过的窗口；0 表示首个 CHANGE_INTERVAL 内不换句
        self._last_rotate_bucket = 0

        self.thinking_bar_message_content = "Digging..."
        self.thinking_bar_tip_message_content = None
        # 呼吸开关；只打主行那颗⬡
        self.pointer_blinking = False
        self.pointer_blinking_target = None
        
    def compose(self):
        self.thinking_bar = Horizontal(classes='BottomThinkTip_thinking_bar')
        self.thinking_bar_pointer = Static(content="⬡",classes='BottomThinkTip_thinking_bar_pointer')
        self.pointer_blinking_target = self.thinking_bar_pointer
        self.thinking_bar_message = Static(content=self.thinking_bar_message_content,markup=False,classes='BottomThinkTip_thinking_bar_message')

        self.thinking_bar_tip = Horizontal(classes='BottomThinkTip_thinking_bar_tip')
        self.thinking_bar_tip_pointer = Static(content="⎿",classes='BottomThinkTip_thinking_bar_tip_pointer')
        self.thinking_bar_tip_message = Static(content=self.thinking_bar_tip_message_content or '',markup=False,classes='BottomThinkTip_thinking_bar_tip_message')
        self.thinking_bar_tip.display = False

        with self.thinking_bar:
            yield self.thinking_bar_pointer
            yield self.thinking_bar_message

        with self.thinking_bar_tip:
            yield self.thinking_bar_tip_pointer
            yield self.thinking_bar_tip_message

        
    @on(Mount)
    def _mount_handler(self):
        self._timer = self.set_interval(1.0,self._refresh_timer)
        self._start_pointer_blinking()


    def _refresh_timer(self):
        self.elapsed_time = monotonic() - self.start_time
        elapsed_sec = int(self.elapsed_time)
        rotate_bucket = elapsed_sec // CHANGE_INTERVAL

        # 每 CHANGE_INTERVAL 窗口换一句；窗口内只抽一次，跳秒也不连抽
        if rotate_bucket > self._last_rotate_bucket:
            self._last_rotate_bucket = rotate_bucket
            self.thinking_bar_message_content = random.choice(THINING_BAR_MESSAGES)
            self.thinking_bar_tip_message_content = random.choice(THINKING_BAR_TIPS)

        if self.thinking_bar_tip_message_content:
            self.thinking_bar_tip.display = True
        else:
            self.thinking_bar_tip.display = False

        if self.elapsed_time >= CHANGE_INTERVAL:
            self.thinking_bar_message.update(self.thinking_bar_message_content)
            if self.thinking_bar_tip_message_content:
                self.thinking_bar_tip_message.update(self.thinking_bar_tip_message_content)
    
    def finalize(self):
        self._pointer_blinking_stop()
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.remove()


    # 开呼吸：已在闪就跳过
    def _start_pointer_blinking(self):
        if self.pointer_blinking:
            return
        self.pointer_blinking = True
        self._pointer_fade_out()


    # 淡出；animate回调可能晚到，已停则拉回1.0
    def _pointer_fade_out(self):
        if not self.pointer_blinking:
            self.pointer_blinking_target.styles.opacity = 1.0
            return
        self.pointer_blinking_target.styles.animate(
            "opacity",0.3,duration=0.75,
            easing="in_out_sine",
            on_complete=self._pointer_fade_in,
        )


    # 淡入；同上，停了就拉回1.0
    def _pointer_fade_in(self):
        if not self.pointer_blinking:
            self.pointer_blinking_target.styles.opacity = 1.0
            return
        self.pointer_blinking_target.styles.animate(
            "opacity",1.0,duration=0.75,
            easing="in_out_sine",
            on_complete=self._pointer_fade_out,
        )


    # 停呼吸：主行⬡拉回不透明
    def _pointer_blinking_stop(self):
        if not self.pointer_blinking:
            return
        self.pointer_blinking = False
        self.thinking_bar_pointer.styles.animate("opacity",1.0,duration=0)

