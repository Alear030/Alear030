from textual.widgets import Static
from textual.containers import Horizontal
from textual.widget import Widget
from typing import Callable

# ExtraInfoHandler 用于处理extra_info的构建和更新
class ExtraInfoHandler:
    # 初始化ExtraInfoHandler，构建ExtraInfoBuilder和ExtraInfoUpdater
    def __init__(self):
        self.ExtraInfoBuilder:dict[str,callable] = {
            "Static":self._build_static,
            "Horizontal":self._build_horizontal,
            "default":self._build_default
        }
        self.ExtraInfoUpdater:dict[str,callable] = {
            "Static":self._update_static,
            "Horizontal":self._update_horizontal,
            "default":self._update_default
        }
    
    # 处理extra_info，根据extra_info_id构建或更新extra_info
    def extra_info_handler(self,ToolCallWidget:Widget,content:dict):
        self.ToolCallWidget = ToolCallWidget
        self.widget_list = ToolCallWidget.extra_info_widgets
        
        # 获取extra_info_id，如果extra_info_id不存在，则返回
        extra_info_id = content.get("id",None)
        if not extra_info_id:
            return
        
        # 获取extra_info_type，如果extra_info_type不存在，则设置为default
        extra_info_type = content.get("type",None) if content.get("type",None) else "default"

        # 如果extra_info_id不存在，则构建新的extra_info
        if extra_info_id not in self.widget_list.keys():
            new_widget = self.ExtraInfoBuilder[extra_info_type](content)
            ToolCallWidget.extra_body.mount(new_widget)
            self._change_extrabody_display(True)
        else:
            exist_widget_info = self.widget_list[extra_info_id]
            if exist_widget_info["type"] == extra_info_type:
                self.ExtraInfoUpdater[exist_widget_info["type"]](exist_widget_info["widget"],content)
            else:
                # type 变了 → 先移除旧的，再按新 type 重建，确保 widget_list 指向新实例
                exist_widget_info["widget"].remove()
                new_widget = self.ExtraInfoBuilder[extra_info_type](content)
                ToolCallWidget.extra_body.mount(new_widget)
                self._update_widget_list(new_widget,content)
                self._change_extrabody_display(True)
        return
    
    # 改变extra_body的display状态
    def _change_extrabody_display(self,display:bool):
        self.ToolCallWidget.extra_body.display = display
        return
        
    # 处理widget的css
    def _widget_css_handler(self,widget:Widget,content:dict):
        if content.get("css",None):
            for prop,value in content.get("css",{}).items():
                setattr(widget.styles,prop,value)
        return

    # 将new_widget写入ToolCallWidget.extra_info_widgets，id 已在则整条目覆盖（重建后指向新实例）
    def _update_widget_list(self,new_widget:Widget,content:dict):
        widget_id = content.get("id",None)
        if widget_id:
            self.widget_list[widget_id] = {
                "widget":new_widget,
                "type":content.get("type",None) if content.get("type",None) else "default",
                "content":content.get("content",None)
            }
        return


    "以下为ExtraInfoBuilder，不同type对应的构建方式"
    # 构建Static类型的extra_info
    def _build_static(self,content:dict):
        new_widget = Static(
            id=content.get("id",None),
            content=content.get("content",None)
        )
        self._widget_css_handler(new_widget,content)
        self._update_widget_list(new_widget,content)
        return new_widget

    # 构建Horizontal类型的extra_info
    def _build_horizontal(self,content:dict):
        widget_list = []
        for item in content.get("content",[]):
            widget_list.append(self.ExtraInfoBuilder[item.get("type","default")](item))
        new_widget = Horizontal(id=content.get("id",None),*widget_list) 
        self._widget_css_handler(new_widget,content)
        self._update_widget_list(new_widget,content)
        return new_widget
        

    # 构建无法识别的extra_info_type的extra_info
    def _build_default(self,content:dict):
        extra_info = f"Info_ID:{content.get('id',None)} Info_Type:{content.get('type',None)} Info_Content:{content.get('content',None)}"
        new_widget = Static(id=content.get("id",None),content=extra_info)
        self._widget_css_handler(new_widget,content)
        self._update_widget_list(new_widget,content)
        return new_widget

    "以下为ExtraInfoUpdater，不同type对应的更新方式"
    # ExtraInfoUpdater，不同type对应的更新方式
    def _update_static(self,widget:Static,content:dict):
        if content.get("content",None):
            widget.update(content.get("content",None))
        self._widget_css_handler(widget,content)
        self._update_widget_list(widget,content)
        return

    # 更新Horizontal类型的extra_info
    def _update_horizontal(self,widget:Horizontal,content:dict):
        for item in content.get("content",[]):
            self.ExtraInfoUpdater[item.get("type","default")](widget.get_child_by_id(item.get("id",None)),item)
        self._widget_css_handler(widget,content)
        self._update_widget_list(widget,content)
        return

    # 更新无法识别的extra_info_type的extra_info
    def _update_default(self,widget:Static,content:dict):
        extra_info = f"Info_ID:{content.get('id',None)} Info_Type:{content.get('type',None)} Info_Content:{content.get('content',None)}"
        widget.update(extra_info)
        self._widget_css_handler(widget,content)
        self._update_widget_list(widget,content)
        return
