from pathlib import Path
from textual.widgets import Static
from textual.widget import Widget


class TuiWidgets:

    # 初始化创建，负载上widget list
    def __init__(self):
        self.widget_list: dict = {}
        self.css_files:list = []

    # 接受创建
    def widget_register(self, widget_type: str, widget_css_file:Path, widget_enable: bool):

        # 防呆设计，阻止坏数据导致整个widget注册环节崩掉
        if not widget_type:
            raise ValueError('widget_register failled')

        # 装饰器：将被装饰的 widget 类连同元信息一起注册到 widget_list
        def add_widget(widget_cls):
            # 注册widget到widget_list
            self.widget_list[widget_type] = {
                'widget_enable':widget_enable,
                'widget_type':widget_type,
                'widget_cls':widget_cls
            }
            # 注册css到css_files
            if widget_css_file and widget_css_file.exists() and widget_css_file.read_text(encoding='utf-8').strip():
                self.css_files.append(str(widget_css_file))

            return widget_cls

        return add_widget

    # widget构造函数，传入widget type用于区分构造的widget cls 传入dict结构信息，构造的时候widget cls自取
    def build_widget(self,widget_type:str,widget_content:dict|None,widget_id:str=None)->Widget:
        widget_cls = self.widget_list.get(widget_type)

        # 如果传入的widget_content是空，返回一个default样式STATIC占位提示
        if not widget_content:
            return Static(content=f"this {widget_type} message's widget_content is empty",classes='default_css')

        # 未注册或未启用的widget，用默认Static兜底渲染
        if not widget_cls or not widget_cls['widget_enable']:
            return Static(content=f"this {widget_type} message is not enabled",classes='default_css')

        # 已注册且启用的widget，构造时自己从dict取内容
        return widget_cls['widget_cls'](widget_content,widget_id=widget_id)

    # css files 构造返回函数
    def collect_css_files(self)->list[str]:
        css_file_paths = []
        for css_file_path in self.css_files:
            css_file = Path(css_file_path)
            if css_file.exists() and css_file.read_text(encoding='utf-8').strip():
                css_file_paths.append(css_file_path)
        return css_file_paths


# 模块级单例，把注册装饰器挂出来供外部直接使用
tuiwidgets = TuiWidgets()
widget_register = tuiwidgets.widget_register
widget_css_paths = tuiwidgets.collect_css_files

    
        