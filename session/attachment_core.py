from log.log_core import Log

class Attachment:
    # 当前 session 内、按 attachment_target 投给对应 agent 的运行时提示；纯内存态，不持久化、不进入 session_detail
    # 生命周期：waiting 待投 → processing 已渲染进消息但未确认送达 → finished 确认送达，由 recycle 回收
    # 确认这一步由投递方调，Attachment 自己不知道消息到底发没发出去
    # @claude 送达失败的 miss 路径还没做：失败时轮次可能已经对不上，不能简单退回 waiting 重投，
    # _load_attachment 那边也要跟着说明轮次约定。等投递点位从 Loop 抽离之后再一起处理

    def __init__(self):
        self.attachment_list = []  # list[dict]，按插入顺序暂存待渲染的 entry
        self.attachment_status_flag = {"waiting":"waiting","processing":"processing","miss":"miss","finished":"finished"}


    # 新增一条待交付信息；attachment_content 必须是调用方已经语义化好的单条字符串，
    # Attachment 只负责按协议措辞渲染，不解析、不重新加工任何 producer 私有的数据结构
    def attachment_add(self,attachment_type:str,attachment_source:str,attachment_content:str,attachment_target:str):
        self.attachment_list.append({
            "attachment_type": attachment_type,
            "attachment_source": attachment_source,
            "attachment_content": attachment_content,
            "attachment_target":attachment_target,
            "attachment_status":"waiting"
        })


    # 管理attachment消费状态
    def _attachment_status_change(self,attachment_node,status):
        if attachment_node not in self.attachment_list:
            Log.pending_record(level="high",source="attachment",event="attachment_node_status_change_fail",detail={"target_attachment_node":attachment_node,"target_status":status,"detail":"target_attachment_node doesn't exist"})
            return
        if status not in self.attachment_status_flag.keys():
            attachment_node["attachment_status"] = self.attachment_status_flag["miss"]
            Log.pending_record(level="high",source="attachment",event="attachment_node_status_change_fail",detail={"target_attachment_node":attachment_node,"target_status":status,"detail":"target_status_flag doesn't exist"})
            return
        attachment_node["attachment_status"] = self.attachment_status_flag[status]

    
    # 单条 attachment 按协议措辞渲染：notification 与 interrupt 对 main agent 的行为要求不同，
    # 措辞本身就是行为指令；未显式声明为 interrupt 的一律按 notification 处理，不做枚举校验
    def _load_attachment(self,attachment_node:dict,attachment_target)->str:
        if attachment_node["attachment_status"] != "waiting" or attachment_node["attachment_target"] != attachment_target:
            return
        
        assemble_node = ""
        if attachment_node['attachment_type'] == 'interrupt':
            assemble_node = (
                f"[需要优先处理 | 来源: {attachment_node['attachment_source']}]\n"
                f"{attachment_node['attachment_content']}\n"
                "请先处理该事项，完成后再恢复处理用户本轮原始请求；"
                "未经上述内容明确授权，不得自行执行有副作用的操作。"
            )
        else:
            assemble_node =  (
                f"[系统通知 | 来源: {attachment_node['attachment_source']}]\n"
                f"{attachment_node['attachment_content']}\n"
                "仅供知晓，无需为此打断当前任务，也无需向用户特别说明或调用确认工具。"
            )
        # 渲染即视为已投出，状态统一走 _attachment_status_change，不在这里直接改字段
        self._attachment_status_change(attachment_node=attachment_node,status="processing")
        return assemble_node


    # 按插入顺序渲染当前暂存的全部 attachment_node
    # 无待渲染内容时返回空串，调用方无需先判空即可直接拼接
    def attachment_render(self,attachment_target)->str:
        if not self.attachment_list:
            return ''

        loaded_attachment = [self._load_attachment(attachment_node,attachment_target) for attachment_node in self.attachment_list]

        # 非 waiting、或不是投给本 target 的 node,在 _load_attachment 里返回 None,滤掉再 join,否则 join 当场崩
        # 一条都没轮到时一并返回空串,不发只有壳没有内容的 system-reminder
        waiting_attachment = [loaded_node for loaded_node in loaded_attachment if loaded_node]
        if not waiting_attachment:
            return ''

        joined = '\n\n'.join(waiting_attachment)

        return (
            "<system-reminder>\n"
            "以下为系统在本轮注入的运行时信息，并非用户输入。\n\n"
            f"{joined}\n"
            "</system-reminder>"
        )

    # 每轮loop结束之后，进行finished处理，且只有在loop正常结束而非中途报错的情况下通过触发hook的方式来收尾
    # status 传字面量，合法性交给 _attachment_status_change 统一认
    def attachment_round_finish(self):
        for attachment_node in self.attachment_list:
            if attachment_node["attachment_status"] == "processing":
                self._attachment_status_change(attachment_node=attachment_node,status="finished")

    # 清空所有待渲染 entry；由调用方（未来的 Loop）在整轮 ReAct 结束后调用，避免泄漏到后续回合
    # 走到这里还是 processing，说明 attachment_round_finish 没跑到（loop 中途报错），等同没送成，标 miss
    # 先定状态、再按状态重建列表，两趟走：只有 finished 出局，miss 留着等后续处理
    def attachment_recycle(self):
        for attachment_node in self.attachment_list:
            if attachment_node["attachment_status"] == "processing":
                self._attachment_status_change(attachment_node=attachment_node,status="miss")

        self.attachment_list = [
            attachment_node for attachment_node in self.attachment_list
            if attachment_node["attachment_status"] != "finished"
        ]