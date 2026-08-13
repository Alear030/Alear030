from ...tui_widgets_core import widget_register

from pathlib import Path

from textual import on, events
from textual.events import Mount
from textual.widget import Widget
from textual.widgets import Input, Static
from textual.containers import Vertical, Horizontal

from typing import Callable

css_file = Path(__file__).parent / 'widget_css.tcss'


# 解析question_info → question_area_list，供compose挂载和后续切题/高亮查表
def _build_question_area_list(question_info:list)->list:
    is_multi_question = len(question_info or []) > 1
    question_area_list = []
    # 逐题：index写入各节点id，compose里用question_area.display按index显隐切题
    for index,question in enumerate(question_info or []):
        # question_area：一整题的外壳Vertical；id带index，切题时按ASK_USER_QUESTION_QUESTION_AREA_{index}找
        question_area = Vertical(classes='AskUserQuestion_question_area',id=f"ASK_USER_QUESTION_QUESTION_AREA_{index}")
        # question_content：显示本题question文案的Static
        question_content = Static(content=question.get("question","") or "",classes="AskUserQuestion_question_content")
        # question_options_area：承装本题全部选项行的Vertical
        question_options_area = Vertical(classes='AskUserQuestion_question_options_area')
        question_options_list = []

        # 判多选：只认 multi-option=True；多选label前挂[ ]，单选不挂只靠>高亮
        is_multi = question.get("multi-option") is True

        options = question.get("options") or []
        # 逐行：i∈[0,len(options)]，末位i==len(options)挂自行输入Input，其后另挂 next/submit；其余为普通选项
        for i in range(len(options) + 1):
            question_option_item_vertical = Vertical(classes='AskUserQuestion_question_option_item_vertical')
            # pointer与label横排（普通选项与末位自行输入共用）
            question_option_item_horizontal = Horizontal(classes='AskUserQuestion_question_option_item_horizontal')
            # pointer：首项>其余空格；id=POINTER_{题index}_{选项i}，↑↓高亮按此改
            question_option_item_pointer = Static(
                content=">" if i == 0 else " ",
                classes="AskUserQuestion_question_option_item_pointer",
                id=f"ASK_USER_QUESTION_QUESTION_OPTION_ITEM_POINTER_{index}_{i}",
            )
            if i == len(options):
                # 末位自行输入行：pointer+序号label + Input；id只带题index供↑↓focus
                question_option_item_label = Static(
                    content=f'{i+1}. {("[ ] " if is_multi else "")}',
                    classes="AskUserQuestion_question_option_item_label",
                )
                question_option_userInput = Input(
                    placeholder="Type something",
                    classes="AskUserQuestion_question_option_userInput",
                    id=f"ASK_USER_QUESTION_QUESTION_OPTION_USER_INPUT_{index}",
                )
                question_options_list.append({
                    "question_option_item_vertical":question_option_item_vertical,
                    "question_option_item_horizontal":question_option_item_horizontal,
                    "question_option_item_pointer":question_option_item_pointer,
                    "question_option_item_label":question_option_item_label,
                    "question_option_userInput":question_option_userInput,
                })
                # 单选：选完由 Enter 切题/提交，不挂 next/submit；多选才挂操作行
                if not is_multi:
                    continue
                # Input 后再挂独立 next/submit 行（新 Vertical/Horizontal/pointer，不复用上行）
                # action_i=len(options)+1：紧接 Input 下一档，POINTER id 用 {index}_{action_i} 给↑↓对齐
                action_i = len(options) + 1
                # 单题或末题→submit，多题非末题→next；写入 dict 供后续按键认行
                row_action = "submit" if (not is_multi_question or index == len(question_info) - 1) else "next"
                question_option_item_vertical = Vertical(classes='AskUserQuestion_question_option_item_vertical')
                question_option_item_horizontal = Horizontal(classes='AskUserQuestion_question_option_item_horizontal')
                # pointer 先空格：默认>仍在首行，↑↓移到本行才改>
                question_option_item_pointer = Static(
                    content=" ",
                    classes="AskUserQuestion_question_option_item_pointer",
                    id=f"ASK_USER_QUESTION_QUESTION_OPTION_ITEM_POINTER_{index}_{action_i}",
                )
                question_option_item_label = Static(
                    content=row_action,
                    classes="AskUserQuestion_question_option_item_label",
                )
                # 带 row_action，与普通选项/userInput 区分
                question_options_list.append({
                    "question_option_item_vertical":question_option_item_vertical,
                    "question_option_item_horizontal":question_option_item_horizontal,
                    "question_option_item_pointer":question_option_item_pointer,
                    "question_option_item_label":question_option_item_label,
                    "row_action":row_action,
                })
                continue
            # label：序号 + 多选[ ] + 选项文案
            question_option_item_label = Static(
                content=f'{i+1}. {("[ ] " if is_multi else "")}{options[i].get("label","") if isinstance(options[i],dict) else ""}',
                classes="AskUserQuestion_question_option_item_label",
            )
            # description：选项下方灰字说明
            question_option_item_description = Static(
                content=(options[i].get("description") or options[i].get("value") or "") if isinstance(options[i],dict) else "",
                classes="AskUserQuestion_question_option_item_description",
            )
            question_options_list.append({
                "question_option_item_vertical":question_option_item_vertical,
                "question_option_item_horizontal":question_option_item_horizontal,
                "question_option_item_pointer":question_option_item_pointer,
                "question_option_item_label":question_option_item_label,
                "question_option_item_description":question_option_item_description,
            })

        # 收进list：is_multi留给后面勾选逻辑；其余给compose yield
        question_area_list.append({
            "is_multi":is_multi,
            "question_area":question_area,
            "question_content":question_content,
            "question_options_area":question_options_area,
            "question_options_list":question_options_list,
        })
    return question_area_list


@widget_register(widget_type="AskUserQuestion",widget_css_file=css_file,widget_enable=True)
class AskUserQuestion(Widget):
    can_focus = True

    def __init__(self,widget_content:dict|None=None,widget_type="AskUserQuestion",widget_id:str=None,event_stop:Callable=None):
        super().__init__(classes='AskUserQuestion')
        self.content = widget_content or {}
        self.widget_id = widget_id or "ASK_USER_QUESTION"

        self.question_info = self.content.get("question_info") or []
        self.queue = self.content.get("queue",None)

        self.question_area_list = _build_question_area_list(self.question_info)
        self.current_question_index = 0
        self.current_option_index = 0
        self.is_multi_question = len(self.question_info) > 1

        self._is_submitted = False
        self.event_stop = event_stop

    def compose(self):
        with Vertical(classes='AskUserQuestion_vertical'):

            # 如果是多个问题，显示头部的tab，能够使用←和→切换问题
            if self.is_multi_question:
                with Horizontal(classes='AskUserQuestion_header'):
                    yield Static(content="←",classes="AskUserQuestion_header_left")
                    for i,question in enumerate(self.question_info):
                        mark = "[ ]"
                        header_text = (question.get("header") or question.get("question") or "").strip()
                        yield Static(
                            content=f"{mark} {header_text}",
                            classes="AskUserQuestion_header_question",
                            id=f"ASK_USER_QUESTION_HEADER_QUESTION_{i}",
                        )
                    yield Static(content="submit",classes="AskUserQuestion_header_preview")
                    yield Static(content="→",classes="AskUserQuestion_header_right")

            # 逐题挂载：index与QUESTION_AREA_{index}对齐，compose里用display按index显隐切题
            for index,item in enumerate(self.question_area_list):
                question_area = item["question_area"]
                # question_area → content + options_area
                with question_area:
                    yield item["question_content"]
                    with item["question_options_area"]:
                        # 逐行：vertical→horizontal(pointer+label)→description/userInput
                        for option in item["question_options_list"]:
                            with option["question_option_item_vertical"]:
                                with option["question_option_item_horizontal"]:
                                    yield option["question_option_item_pointer"]
                                    yield option["question_option_item_label"]
                                # 三态：userInput / description 再挂子节点；next·submit 行只有 horizontal 内 pointer+label，此处不 yield
                                if option.get("question_option_userInput") is not None:
                                    yield option["question_option_userInput"]
                                elif option.get("question_option_item_description") is not None:
                                    yield option["question_option_item_description"]
                                # else：row_action 行，不再挂子节点
                # index==0只显首题，其余先藏；←→切题时再改display
                question_area.display = (index == 0)
    
    # 挂载时focus到第一个问题
    @on(Mount)
    def widget_mounted(self):
        self.focus()

    # keyboard event
    @on(events.Key)
    def key_handler(self,event:events.Key):
        if event.key == "up" or event.key == "down":
            self._up_down_handler(event.key)
            event.stop()
            return
        
        elif event.key == "left" or event.key == "right":
            self._left_right_handler(event.key)
            event.stop()
            return
        
        elif event.key == "enter":
            self._enter_handler()
            event.stop()
            return

    @on(Input.Submitted)
    def _userInput_submitted(self,event:Input.Submitted):
        self._enter_handler()
        event.stop()
        return

    # input类型问题，保存用户输入为答案
    @on(Input.Changed)
    def _userInput_changed(self,event:Input.Changed):
        current_question = self.question_area_list[self.current_question_index]
        current_question_isMulti = current_question["is_multi"]

        text = (event.input.value or "").strip()

        answer = self.question_info[self.current_question_index].get("answer")
        if not isinstance(answer,dict):
            answer = {"options":[],"user_input":None}
        answer["user_input"] = text if text else None
        self.question_info[self.current_question_index]["answer"] = answer
        
        if not current_question_isMulti:
            return
        for row in current_question["question_options_list"]:
            if row.get("question_option_userInput") is None:
                continue
            n = len(self.question_info[self.current_question_index].get("options")or[])+1

            if text:
                row["question_option_item_label"].update(f"{n}. [✅️]")
            else:
                row["question_option_item_label"].update(f"{n}. [ ]")
            break


    # ↑↓：只挪本题 pointer，不写 question_anwser
    def _up_down_handler(self,direction:str):
        options_list = self.question_area_list[self.current_question_index]["question_options_list"]
        if direction == "up":
            # 已在首行，顶死
            if self.current_option_index == 0:
                return
            # 上一行亮>，当前行清成空格，再回退 current_option_index
            options_list[self.current_option_index - 1]["question_option_item_pointer"].update(">")
            options_list[self.current_option_index]["question_option_item_pointer"].update(" ")
            self.current_option_index -= 1
        elif direction == "down":
            # 已在末行（含自行输入），顶死
            if self.current_option_index == len(options_list) - 1:
                return
            # 下一行亮>，当前行清成空格，再推进 current_option_index
            options_list[self.current_option_index + 1]["question_option_item_pointer"].update(">")
            options_list[self.current_option_index]["question_option_item_pointer"].update(" ")
            self.current_option_index += 1

        # 落到自行输入行 → focus Input；否则 focus 回 AskUserQuestion
        now_row = options_list[self.current_option_index]
        user_input = now_row.get("question_option_userInput")
        if user_input is not None:
            user_input.focus()
            return
        self.focus()

    # ←→：多题才切；先reset离开题，再对调question_area.display，最后改current_question_index
    def _left_right_handler(self,direction:str):
        if not self.is_multi_question:
            return
        if direction == "left":
            # 已在第一题，顶死
            if self.current_question_index == 0:
                return
            self._reset_question_item_pointer(self.current_question_index)
            # 亮上一题，藏当前题
            self.question_area_list[self.current_question_index - 1]["question_area"].display = True
            self.question_area_list[self.current_question_index]["question_area"].display = False
            self.current_question_index -= 1
        elif direction == "right":
            # 已在最后一题，顶死
            if self.current_question_index == len(self.question_area_list) - 1:
                return
            self._reset_question_item_pointer(self.current_question_index)
            # 亮下一题，藏当前题
            self.question_area_list[self.current_question_index + 1]["question_area"].display = True
            self.question_area_list[self.current_question_index]["question_area"].display = False
            self.current_question_index += 1

        self.focus()

    # 离开某题时：pointer全部清空格，首行重新亮>，current_option_index归零（再进来从首行开始）
    def _reset_question_item_pointer(self,question_index:int):
        options_list = self.question_area_list[question_index]["question_options_list"]
        for option in options_list:
            option["question_option_item_pointer"].update(" ")
        options_list[0]["question_option_item_pointer"].update(">")
        self.current_option_index = 0

    # Enter：单选提交；多选切题/提交
    def _enter_handler(self):

        if self._is_submitted:
            return

        current_question = self.question_area_list[self.current_question_index]
        current_row = current_question["question_options_list"][self.current_option_index]
        current_question_isMulti = current_question["is_multi"]
        
        # 如果当前题目是单独题而非多问题，判断是否为多选，如果是多选，需要submit提交，如果是单选，直接提交
        row_action = current_row.get("row_action")
        if row_action == "submit":
            self._submit_handler()
            return
        elif row_action == "next":
            self._left_right_handler("right")
            return

        # 自行输入行：多选已由 Changed 写过，Enter 不做事；单选有字才推进
        if current_row.get("question_option_userInput") is not None:
            if current_question_isMulti:
                return
            answer = self.question_info[self.current_question_index].get("answer")
            if not isinstance(answer,dict) or not answer.get("user_input"):
                return
            answer["options"] = []
            self._after_single_answered()
            return

        # 普通选项：单选选过或选过标记，多选勾过或勾过标记
        answer = self.question_info[self.current_question_index].get("answer")
        if not isinstance(answer,dict):
            answer = {"options":[],"user_input":None}
            self.question_info[self.current_question_index]["answer"] = answer
        
        answer_selected = answer.get("options")
        if not isinstance(answer_selected,list):
            answer_selected = []
            answer["options"] = answer_selected
        
        option_i = self.current_option_index
        options = self.question_info[self.current_question_index].get("options") or []
        option = options[option_i]
        label_text = option.get("label") if isinstance(option,dict) else ""

        if current_question_isMulti:
            if option in answer_selected:
                answer_selected.remove(option)
                current_row["question_option_item_label"].update(f"{option_i+1}. [ ] {label_text}")
            else:
                answer_selected.append(option)
                current_row["question_option_item_label"].update(f"{option_i+1}. [✅️] {label_text}")
        else:
            # 单选：只留这一项；高亮当前 label，其余恢复默认色
            for row in current_question["question_options_list"]:
                if row.get("question_option_userInput") is not None or row.get("row_action") is not None:
                    continue
                row["question_option_item_label"].styles.color = None
            current_row["question_option_item_label"].styles.color = "rgb(0,128,0)"
            answer_selected.clear()
            answer_selected.append(option)
            answer["user_input"] = None
            self._after_single_answered()
    
    def _after_single_answered(self):
        if self.is_multi_question and self.current_question_index < len(self.question_area_list) - 1:
            self._left_right_handler("right")
            return
        self._submit_handler()
    
    def _submit_handler(self):
        if self.queue is None or self._is_submitted:
            return
        self.queue.put(self.question_info)
        self._is_submitted = True
        if self.event_stop is not None:
            self.event_stop(event_type = "AskUserQuestion", event_widget = self)