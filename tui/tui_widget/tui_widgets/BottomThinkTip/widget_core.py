from ...tui_widgets import widget_register
from .widget_tip_messages import THINKING_BAR_MESSAGES, THINKING_BAR_TIPS

from time import monotonic
from pathlib import Path
from textual import on
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal
from textual.events import Mount
import random


css_file = Path(__file__).parent/'widget_css.tcss'

# 换句间隔上下界；每次轮换重抽
CHANGE_INTERVAL_MIN = 4
CHANGE_INTERVAL_MAX = 6


@widget_register(widget_type="BottomThinkTip",widget_css_file=css_file,widget_enable=True)
class BottomThinkTip(Widget):
    # 底栏置底条：主行⬡+轮换文案，脚注⎿+tip；LoopEnd finalize卸
    def __init__(self,widget_content:dict=None,widget_id:str=None):
        super().__init__(classes='BottomThinkTip')
        self.widget_id = widget_id

        # 计时：mount起跑，finalize停
        self.start_time = monotonic()
        self.elapsed_time = 0
        self._timer = None
        # 下次换句阈值；首段Digging...到点前不换
        self._next_rotate_at = random.randint(CHANGE_INTERVAL_MIN,CHANGE_INTERVAL_MAX)

        # 文案权威；tip None则藏脚注行
        self.thinking_bar_message_content = "Digging..."
        self.thinking_bar_tip_message_content = None
        
        # 呼吸开关；只打主行那颗⬡
        self.pointer_blinking = False
        self.pointer_blinking_target = None
        
    def compose(self):
        # 主行：⬡ + 轮换主文案
        self.thinking_bar = Horizontal(classes='BottomThinkTip_thinking_bar')
        self.thinking_bar_pointer = Static(content="⬡",classes='BottomThinkTip_thinking_bar_pointer')
        self.pointer_blinking_target = self.thinking_bar_pointer
        self.thinking_bar_message = Static(content=self.thinking_bar_message_content,markup=False,classes='BottomThinkTip_thinking_bar_message')

        # 脚注：⎿ + tip；抽到内容才显示
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

        
    # mount：1秒tick驱动换句，开呼吸
    @on(Mount)
    def _mount_handler(self):
        self._timer = self.set_interval(1.0,self._refresh_timer)
        self._start_pointer_blinking()


    def _refresh_timer(self):
        self.elapsed_time = monotonic() - self.start_time
        elapsed_sec = int(self.elapsed_time)

        # 到阈值换句并重抽间隔；跳秒也只换一次
        if elapsed_sec >= self._next_rotate_at:
            self.thinking_bar_message_content = random.choice(THINKING_BAR_MESSAGES)
            self.thinking_bar_tip_message_content = random.choice(THINKING_BAR_TIPS)
            self._next_rotate_at = elapsed_sec + random.randint(CHANGE_INTERVAL_MIN,CHANGE_INTERVAL_MAX)
            self.thinking_bar_message.update(self.thinking_bar_message_content)
            if self.thinking_bar_tip_message_content:
                self.thinking_bar_tip_message.update(self.thinking_bar_tip_message_content)

        # tip有内容才露脚注行
        if self.thinking_bar_tip_message_content:
            self.thinking_bar_tip.display = True
        else:
            self.thinking_bar_tip.display = False
    
    # LoopEnd收尾：停呼吸+timer，卸widget
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

