class Attachment:
    # 当前 session 内、仅供 main agent 本轮消费的运行时提示；纯内存态，不持久化、不进入 session_detail

    def __init__(self):
        self.attachment_list = []  # list[dict]，按插入顺序暂存待渲染的 entry


    # 新增一条待交付信息；attachment_content 必须是调用方已经语义化好的单条字符串，
    # Attachment 只负责按协议措辞渲染，不解析、不重新加工任何 producer 私有的数据结构
    def attachment_add(self,attachment_type:str,attachment_source:str,attachment_content:str):
        self.attachment_list.append({
            "attachment_type": attachment_type,
            "attachment_source": attachment_source,
            "attachment_content": attachment_content,
        })


    # 单条 entry 按协议措辞渲染：notification 与 interrupt 对 main agent 的行为要求不同，
    # 措辞本身就是行为指令；未显式声明为 interrupt 的一律按 notification 处理，不做枚举校验
    def _render_entry(self,entry:dict)->str:
        if entry['attachment_type'] == 'interrupt':
            return (
                f"[需要优先处理 | 来源: {entry['attachment_source']}]\n"
                f"{entry['attachment_content']}\n"
                "请先处理该事项，完成后再恢复处理用户本轮原始请求；"
                "未经上述内容明确授权，不得自行执行有副作用的操作。"
            )

        return (
            f"[系统通知 | 来源: {entry['attachment_source']}]\n"
            f"{entry['attachment_content']}\n"
            "仅供知晓，无需为此打断当前任务，也无需向用户特别说明或调用确认工具。"
        )


    # 按插入顺序渲染当前暂存的全部 entry，返回可直接拼进模型消息的字符串；
    # 无待渲染内容时返回空串，调用方无需先判空即可直接拼接
    def attachment_render(self)->str:
        if not self.attachment_list:
            return ''

        rendered_entries = [self._render_entry(entry) for entry in self.attachment_list]
        joined = '\n\n'.join(rendered_entries)

        return (
            "<system-reminder>\n"
            "以下为系统在本轮注入的运行时信息，并非用户输入。\n\n"
            f"{joined}\n"
            "</system-reminder>"
        )


    # 清空所有待渲染 entry；由调用方（未来的 Loop）在整轮 ReAct 结束后调用，避免泄漏到后续回合
    def attachment_clear(self):
        self.attachment_list.clear()