import json
import re


from agent.agent_core import Agent
from loop import Loop
from concurrent.futures import ThreadPoolExecutor,as_completed


from memory.memory_prompt import memory_prompts
from memory.memory_config.memory_config_core import memory_config
from memory.memory_storage import memory_storage


# memory整体设计思路：
# 负责任务：slice接收&分类、slice节点储存、slice节点分类后处理、记忆处理
# 后续应该将slice和summary的逻辑兼容进来，现在先不动


class Memory:
    def __init__(self,memory_agent:Agent,loop:Loop = None):
        # memory agents 相关
        self.memory_agent = memory_agent
        self.loop = loop

        # memory type 相关
        self.memory_type = memory_config.get_memory_config(file_name='memory_type')


    # memory_agent 后续需要多种场景的处理、输入以及输出，所以需要一个更替prompt的方法适配，避免过多subagent导致冗余
    def _switch_prompt(self,type:str = None):
        # 每次切换模式说明对应场景任务已经完成，清空message_list同时更换system_prompt
        
        if type == 'memory_type':
            self.memory_agent.message_list = [{'role':'system','content':memory_prompts.get_memory_type_prompt()}]
        
        if type == 'user_info':
            self.memory_agent.message_list = [{'role':'system','content':memory_prompts.get_user_info_prompt()}]


    # 将某个type_name的type_feature合并进内存中的特征库：新特征直接追加，追加后超过10条则以模型返回的完整合并结果整体替换（模型按prompt规则已经算好了合并后的全量结果）
    def _update_memory_type(self,type_name:str,type_feature:list[str]):
        for entry in self.memory_type:
            if entry['type_name'] != type_name:
                continue
            existing = entry['type_feature']
            new_items = [f for f in type_feature if f not in existing]
            if not new_items:
                return
            merged = existing + new_items
            entry['type_feature'] = type_feature if len(merged) > 10 else merged
            memory_config.update_memory_config(file_name='memory_type',file_content=self.memory_type)
            return


    # 对传入的slcie进行type的划分
    def slice_type_define(self,slice:dict,messages):
            # 切换memory_agent的system_prompt，确保feature更新之后，system_prompt中的{{MEMORY_TYPE_JSON}}是最新的
            self._switch_prompt(type = 'memory_type')
            self.memory_agent.refresh_agent_level(agent_level='medium_level')

            # 拼接传入memory_agent的信息
            input_info = {
                "slice_info":{
                    "topic":slice['slice_anchor']['topic'],
                    "key_words":slice['slice_anchor']['key_words'],
                    "summary_detail":slice['slice_anchor']['summary_detail']
                },
                "message_list":[]
            }

            # 得到对应slice的message_list
            start_round = slice['start_round']
            end_round = slice['end_round']
            for msg in messages:
                if msg['message_round'] >= start_round and msg['message_round'] <= end_round:
                    input_info['message_list'].append(msg)

            # 单次独立分类：只带当前system_prompt+本次slice内容，不污染memory_agent常驻的message_list
            input_message = [
                {"role":"system","content":self.memory_agent.message_list[0]['content']},
                {"role":"user","content":json.dumps(input_info,ensure_ascii=False,indent=2)}
            ]

            rq = self.memory_agent.agent_ai.chat.completions.create(model=self.memory_agent.model_name,messages=input_message).choices[0].message.content.strip()

            # 剥离可能出现的markdown代码块(与_session_slice_summary的防御性解析保持一致)
            m = re.match(r'^```(?:json)?\s*\n(.*?)\n```\s*$', rq, re.DOTALL)
            if m:
                rq = m.group(1).strip()

            # 解析memory_agent回复json
            try:
                rq_json = json.loads(rq)
            except json.JSONDecodeError:
                return None

            # 判断结果是否无分类命中([{"result":null}])
            if not rq_json or 'result' in rq_json[0]:
                return slice # @claude 检查这里是否应该返回slice 后续这个方法要链接存储节点

            # 存在返回结果，逐个type_name更新特征库(新增/合并)，同时收集本slice的分类标签
            slice_tag = []
            for result in rq_json:
                type_name:str = result['type_name']
                type_feature:list = result['type_feature']
                slice_tag.append({"type_name":type_name,"type_feature":type_feature})
                self._update_memory_type(type_name,type_feature)

            # 存在返回的结果，将slice进行拼装并返回对应结果(一个slice可能命中多个type)
            # done(@claude): 防重复提取改在 slices_pipeline 层用身份去重(按session_id+start+end跳过已入库片)+锁内二次去重解决,不在此处加标志字段——slice_node的"存在"本身即"处理过"的证据,符合派生层可重建/不反写原文的红线
            slice_data = {
                "session_id": slice['session_id'],
                "time_stamp": slice['time_stamp'],
                "start_round": slice['start_round'],
                "end_round": slice['end_round'],
                "slice_type": [tag['type_name'] for tag in slice_tag],
                "slice_embedding": slice['slice_embedding'],
                "slice_anchor": {
                    "topic": slice['slice_anchor']['topic'],
                    "key_words": slice['slice_anchor']['key_words'],
                    "summary_detail": slice['slice_anchor']['summary_detail'],
                    }
                }

            return slice_data


    # 接收slice分type同时储存到slice_node.json中,接收slice dict和 对应的messages包含toolcall和toolresult
    def slices_type_define(self,slices:list[dict],messages:list[dict]):
        
        # 对传入的slcies进行分类处理入口，得到一次性传入的slcies的分类结果，并进行分类处理
        slice_type_results = []
        for acr_slice in slices:
            slice_result = self.slice_type_define(slice=acr_slice,messages=messages)
            # 判断是否被分类，两种储存方式
            if slice_result is not None:
                slice_type_results.append(slice_result)
            else:
                slice_type_results.append(acr_slice)

        return slice_type_results# @claude(ignore) 这里后续要接入存储，新增一个def进行存储
    
    # slice分类后按照slice_type进行分类处理

    # slice_type 存在user_info，需要将存在user_info的slice进行用户信息的提取
    # 同时需要将自涌现的user_info.json进行比较和处理回存
    # 这里memory_agent需要loop执行工具
    # extra_message 实际上是给可能插入的话题进行收口，比如main_agent的主动调用->tool
    def user_info_extract(self,slice_data:dict=None,messages:list[dict]=None,extra_message:str=None,force:bool=False)->list:
        self._switch_prompt(type='user_info')# 切换memory_agent's system_prompt
        self.memory_agent.refresh_agent_level(agent_level='max_level')
        # 判断当前slice是否存在type_name为user_info或者force为true，不满足就直接返回slice_data
        if 'user_info' not in slice_data['slice_type'] and not force:
            return slice_data
        
        # 如果满足开始拼接message
        input_msg = []
        input_info = {
                "slice_info":{
                    "topic":slice_data['slice_anchor']['topic'],
                    "key_words":slice_data['slice_anchor']['key_words'],
                    "summary_detail":slice_data['slice_anchor']['summary_detail'],
                    "session_id":slice_data['session_id'],
                    "time_stamp":slice_data['time_stamp'],
                    "start_round":slice_data['start_round'],
                    "end_round":slice_data['end_round']
                },
                "message_list":[]
            }

        # 得到对应slice的message_list
        start_round = slice_data['start_round']
        end_round = slice_data['end_round']
        for msg in messages:
            if msg['message_round'] >= start_round and msg['message_round'] <= end_round:
                input_info['message_list'].append(msg)

        # 得到最后的传入消息列表,并传入loop同时得到返回的json
        input_msg.append({"role":"user","content":input_info})
        rq = self.loop.loop_run(agent=self.memory_agent,message=str(json.dumps(input_msg,ensure_ascii=False,indent=2)))

        m = re.match(r'^```(?:json)?\s*\n(.*?)\n```\s*$', rq, re.DOTALL)
        if m:
            rq = m.group(1).strip()

        rq_json = json.loads(rq)# @claude 解析隔离异常

        # 过滤掉没有 info_source 的条目(无来源=不可靠,不入库;符合"只提取有据可依信息"原则)
        for dim in rq_json:
            if 'info_list' in dim:
                dim['info_list'] = [info for info in dim['info_list'] if info.get('info_source')]

        # 将返回结果传回给user.json
        memory_storage.update_memory_storage(file_name='user',file_content=rq_json)

        return rq_json


    # 开始处理user_info_json
    def user_info_reform(self,rq_json):
        # # 本函数说明：处理memmory_agent在user_info_extract输出的信息，然后对D:\Alear030\memory\memory_config\memory_configs\user_info.json 中的参考模板进行处理
        # ## 处理类型
        # 1 - type_name\type_desc\type_feature 全部已有 - 不处理
        # 2 - type_name\type_desc已有 type_feature变更 - 新增
        # 3 - type_name 存在 type_desc变更 - 覆盖type_desc
        # 4 - type_name 不存在 分情况
        # 4-1 type_name新增 - 添加tpyename\typedesc\typefeature
        # 4-2 type_name合并 - 靠rq_json里合并后维度自带的merged_from(被吸收掉的旧type_name列表)精确删除，不靠"缺席即删"的猜测(避免误删还没攒到info的种子维度)

        # 读取当前提取维度模板(每条仅 type_name/type_desc/type_feature，无 info_list)
        template = memory_config.get_memory_config(file_name='user_info')

        # 先扫一遍收集所有被合并掉的旧维度名(case 4-2)：merged_from里、且不等于合并后保留名的
        merged_away = set()
        for dim in rq_json:
            for old_name in dim.get('merged_from', []):
                if old_name != dim['type_name']:
                    merged_away.add(old_name)

        # 删除被合并掉的旧维度
        if merged_away:
            template = [entry for entry in template if entry['type_name'] not in merged_away]

        # 按 type_name 建索引，便于逐个维度比对(引用与template内的dict一致，改索引即改template)
        template_index = {entry['type_name']: entry for entry in template}

        # 逐个处理rq_json维度
        for dim in rq_json:
            type_name = dim['type_name']
            type_desc = dim['type_desc']
            type_feature = dim['type_feature']

            existing = template_index.get(type_name)

            # case 4-1：模板中不存在该维度 → 新增(只留三字段，剥掉info_list/merged_from)
            if existing is None:
                new_entry = {
                    "type_name": type_name,
                    "type_desc": type_desc,
                    "type_feature": list(type_feature),
                }
                template.append(new_entry)
                template_index[type_name] = new_entry
                continue

            # case 3：type_desc变更 → 覆盖
            if existing['type_desc'] != type_desc:
                existing['type_desc'] = type_desc

            # case 2：type_feature有新项 → 追加(去重保序，复用_update_memory_type的思路)
            new_features = [f for f in type_feature if f not in existing['type_feature']]
            if new_features:
                existing['type_feature'] = existing['type_feature'] + new_features

            # case 1：type_name/type_desc/type_feature全部已有 → 上面两个判断都不触发，自然不处理

        # 回写模板
        memory_config.update_memory_config(file_name='user_info', file_content=template)
        

    # done(@claude): 修复三处bug——存储存的是分类后结果而非原始切片、遍历范围收窄到本次新片、slice_type字段名与传参修正
    # 方法说明：将切片的分类、存储、按照type分配管道进行统合，方便hook直接对接
    def slices_pipeline(self,slices:list[dict],messages:list[dict]):
        # done(@claude): 尾片排除 slices[:-1] 挪到 hook 做传入数据预处理,memory_core 只接定型片直接处理;身份去重留在本层(读 memory_storage 属内部状态)
        # 入参 slices 已由 hook 预处理:排除了仍在生长的尾片,均为定型可处理片
        if not slices:
            return

        # 身份去重(锁外乐观):slice_node 里已按(session_id,start_round,end_round)存在的整片跳过,
        # 连分类 LLM 都省;只有跨轮从没见过的新片才往下走。替代原每轮全量重分类/重提取。
        # 读是无锁的,可能读到过期数据,但这只影响"省不省 LLM",正确性由下面锁内去重兜底。
        existing = memory_storage.get_memory_storage(file_name='slice_node') or []
        seen = {(s['session_id'],s['start_round'],s['end_round']) for s in existing}
        new_slices = [s for s in slices
                      if (s['session_id'],s['start_round'],s['end_round']) not in seen]
        if not new_slices:
            return

        # 切片分类(只分新片)
        slices_type_results = self.slices_type_define(slices=new_slices,messages=messages)

        # 锁内二次去重再入库:防两个 after_round 后台钩子并发时都判定同一片为新片导致重复 extend。
        # actually_new 记录本次锁内确认真正入库的片,下面 user_info 提取严格基于它,并发也不重复提取。
        actually_new = []
        def _dedup_extend(node):
            exist_keys = {(s['session_id'],s['start_round'],s['end_round']) for s in node}
            for s in slices_type_results:
                key = (s['session_id'],s['start_round'],s['end_round'])
                if key not in exist_keys:
                    node.append(s)
                    exist_keys.add(key)
                    actually_new.append(s)
        memory_storage.slice_node_updater(_dedup_extend)

        # 进入管线处理逻辑:只对本轮真正新入库、且命中 user_info 的切片提取(不重复处理历史片)
        for slice in actually_new:
            if 'user_info' in slice.get('slice_type',[]):
                rq_json = self.user_info_extract(slice_data=slice,messages=messages)
                self.user_info_reform(rq_json=rq_json)



        
