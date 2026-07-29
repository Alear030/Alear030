from textual import on,work

from textual.app import App
from textual.widgets import Header,Static,Input,Footer,Markdown
from textual.containers import VerticalScroll,Horizontal
from textual.events import Mount,Click,Unmount

from pathlib import Path

from rich_output import register_output_receiver, unregister_output_receiver


DEFAULT_CSS_PATH = Path(__file__).parent / "tui_style.tcss"


class BreathingPlaceholder(Static):
    """A Static that gently fades in and out while waiting for a result."""

    def on_mount(self):
        self._breathing = True
        self._fade_out()

    def _fade_out(self):
        if not self._breathing:
            return
        self.styles.animate(
            "opacity",
            0.4,
            duration=0.8,
            easing="in_out_sine",
            on_complete=self._fade_in,
        )

    def _fade_in(self):
        if not self._breathing:
            self.styles.opacity = 1.0
            return
        self.styles.animate(
            "opacity",
            1.0,
            duration=0.8,
            easing="in_out_sine",
            on_complete=self._fade_out,
        )

    async def stop_breathing(self):
        self._breathing = False
        await self.app.animator.stop_animation(self.styles,"opacity",complete=False)
        self.styles.opacity = 1.0

    def on_unmount(self):
        self._breathing = False


class Alear030Tui(App):
    TITLE = 'Alear030'

    def __init__(self,run_round = None,session = None,driver_class = None, css_path = str(DEFAULT_CSS_PATH), watch_css = True, ansi_color = None):
        super().__init__(driver_class, css_path, watch_css, ansi_color)
        self.run_round = run_round
        self.session = session

        # Tui's information and sets
        self.title = 'Alear030'
        self.theme = 'rose-pine-dawn'

    # Alear030 Tui 拼接初始的Tui架构
    def compose(self):

        yield Header(show_clock=False,name=self.TITLE)
        yield VerticalScroll(id='content_area')
        yield Input(placeholder='>',id='user_input')
        yield Horizontal(
            Static(id="status_left"),
            Static(id="status_right"),
            id="status_bar",
        )
        # yield Footer(show_command_palette=False)

    # Alear030 TUi init 设置初始input焦点，同时注册中间信息接收器
    @on(message_type=Mount)
    def AlearTui_init(self):
        self.set_focus(self.query_one('#user_input'))
        # 注册 rich_print 接收器，把中间信息流接到 TUI
        register_output_receiver(self._output_receiver)
        self._refresh_status_bar()

    # 从 session.context_tokens 刷新状态栏右侧(used / max);无 session 时跳过
    def _refresh_status_bar(self):
        if self.session is None:
            return
        ctx = self.session.context_tokens
        self.query_one('#status_right', Static).update(
            f'ctx {ctx.used} / {ctx.max_tokens}'
        )

    # 退出时反注册接收器，避免泄漏
    @on(message_type=Unmount)
    def AlearTui_cleanup(self):
        unregister_output_receiver(self._output_receiver)

    # rich_print 的接收器：在工作线程被调用，跳回 UI 线程渲染
    def _output_receiver(self, event_type: str, message: str):
        self.call_from_thread(self._append_event, event_type, message)

    # 在 content_area 追加一个中间事件 widget（UI 线程调用）
    async def _append_event(self, event_type: str, message: str):
        content_area = self.query_one('#content_area', VerticalScroll)
        match event_type:
            case 'agent_thinking':
                # 细线标题 + 隐藏内容，模拟 CC 的 thinking 效果
                # done(@claude): thinking_title 样式保留，thinking_body 加了 margin/border-left/background
                think_title = Static('✦ Alear030 Thinking', classes='thinking_title')
                think_body = Markdown(message, classes='thinking_body')
                think_body.display = False  # 初始隐藏
                content_area.mount(think_title)
                content_area.mount(think_body)
            case 'agent_content':
                # 最终回复通过 run_round 返回值链路展示（round_finished 里 mount Markdown），
                # rich_print 这条是给终端的，TUI 侧跳过避免重复
                return
            case _:
                # 其他事件类型暂不渲染，静默跳过
                return
        content_area.scroll_end(animate=False)


    # Alear030 保证后续无论做什么直都不让user_input失去焦点
    @on(message_type=Click)
    def always_input(self):
        self.set_focus(self.query_one('#user_input'))

    def _thinking_anchor_from_click(self, event: Click):
        """从点击目标向上找到 thinking_title / thinking_body（Markdown 内部子控件也能命中）。"""
        widget = event.widget
        while widget is not None:
            classes = getattr(widget, 'classes', ())
            if 'thinking_title' in classes or 'thinking_body' in classes:
                return widget
            widget = widget.parent
        return None

    def _toggle_thinking_pair(self, anchor) -> None:
        """title 与紧邻 body 成对切换 display，始终只显示其中一个。"""
        content_area = self.query_one('#content_area', VerticalScroll)
        children = list(content_area.children)
        for i, child in enumerate(children):
            if child is not anchor:
                continue
            if 'thinking_title' in child.classes and i + 1 < len(children):
                partner = children[i + 1]
            elif 'thinking_body' in child.classes and i > 0:
                partner = children[i - 1]
            else:
                return
            child.display = not child.display
            partner.display = not partner.display
            return

    # done(@cursor): 不用 CSS 选择器——Click.control 是叶子控件，点 Markdown 文字时不是 .thinking_body；
    # 改为全局 Click + 向上找 title/body，文字区和空白区都能成对切换
    @on(Click)
    def toggle_thinking(self, event: Click):
        anchor = self._thinking_anchor_from_click(event)
        if anchor is None:
            return
        self._toggle_thinking_pair(anchor)
        self.set_focus(self.query_one('#user_input'))

    # 跑一轮loop_run
    @work(thread=True)
    def alear_worker(self,user_message,placeholder):
        try:
            result = self.run_round(message=user_message)
        except Exception as error:
            result = f'[system_error] run_round 执行失败：{error}'
        self.call_from_thread(self.round_finished,placeholder,result)

    async def round_finished(self,placeholder,result):
        """停止呼吸动画，替换占位符为最终回复的 Markdown widget，重新启用输入框并滚到底部。"""
        await placeholder.stop_breathing()
        # 用 Markdown widget 替换掉呼吸占位符：Static 装不下 Markdown 的结构化子块
        content_area = self.query_one('#content_area',VerticalScroll)
        await placeholder.remove()
        content_area.mount(Markdown(f'✦ Alear030: {result}',classes='assistant_message'))

        # 找到user_input并启用 同时 滚动到最下方
        self.query_one("#user_input").disabled = False
        self.query_one('#user_input').focus()
        content_area.scroll_end(animate=False)
        # after_round/compress 已刷新 context_tokens,此处同步到状态栏
        self._refresh_status_bar()

    # 处理user_input 处理 run_round
    @on(message_type=Input.Submitted)
    def Alear_round(self,event:Input.Submitted):
        if not event.value:
            return

        # input 清空 同时将user_input的信息 提交到content_area
        event.input.clear()
        user_message = event.value
        content_area = self.query_one('#content_area',VerticalScroll)
        content_area.mount(Static(content=f'You: {user_message}',classes='user_message'))
        content_area.scroll_end(animate=False)

        # 处理run_round的时候进行占位，同时将input禁用
        placeholder = BreathingPlaceholder(
            content='✦ Alear030 正在思考…',
            classes='thinking_message',
        )
        content_area.mount(placeholder)
        event.input.disabled = True

        self.alear_worker(user_message,placeholder)



if __name__ == "__main__":
    import time
    import random

    def mock_run_round(message: str) -> str:
        """占位伪函数：模拟一轮 loop_run 的耗时与返回。

        仅供 TUI 独立开发/演示，不依赖真实模型与 session。
        真实接入时由外部把 ``loop.loop_run`` 包装成同签名函数传入 ``Alear030Tui``。
        """
        time.sleep(random.uniform(1.5, 2.5))
        return f'收到：{message}（mock 回复）'

    Alear030Tui(run_round=mock_run_round).run()
