import json
import re

from json_repair import repair_json

from rich_output import rich_print


from memory.memory_prompt import memory_prompts
from memory.memory_config.memory_config_core import memory_config
from memory.memory_storage import memory_storage
# 失败诊断仅供本地排查 LLM 输出契约问题，记录 agent 输出与 thinking；项目开源前删除此 import 和对应日志调用，或改为脱敏实现。
from memory.memory_log import memory_log


# memory整体设计思路：
# 负责任务：slice接收&分类、slice节点储存、slice节点分类后处理、记忆处理
# 后续应该将slice和summary的逻辑兼容进来，现在先不动

# @claude(ignore) 说明：
# memory_core 负责外部对接，外部参数引入，同时进行不同memory_X_core 之间的协调
# memory_storage_core 用于将所有涉及到存储，提取等文件读写操作的方法的集成


# advanced_task_node_judge 的三态返回契约:供未来 task 管线按结局路由
# (合并成功收工 / 没匹配上进合成流程 / 处理失败进重试入队)
JUDGE_MERGED = 'merged'
JUDGE_NO_MATCH = 'no_match'
JUDGE_FAILED = 'failed'


# 剥离模型回复外层可能包裹的 markdown 代码块或前缀/后缀文字，定位出真正的 JSON 候选片段。
# 模型常带「确认完毕。」等汇报性前缀，且前缀里可能引用历史片段/示例数组等疑似 JSON 的干扰文本；
# 五份 prompt 的输出契约都要求顶层是数组，真正答案在模型听话时永远在文本最后，
# 因此候选定位统一"从末尾往前找最后一个完整的 [...] 结构"，不取文本中第一个疑似片段。
def _locate_json_candidate(text:str)->str:
    if not text:
        return text
    t = text.strip()
    # 1) 有围栏：取最后一个 ``` 围栏块内部内容(模型偶尔会在分析文字里也带围栏引用旧输出)
    fences = list(re.finditer(r'```(?:json)?\s*\n?(.*?)\n?```', t, re.DOTALL))
    if fences:
        return fences[-1].group(1).strip()
    # 2) 无围栏：从末尾往前找最后一个 ']'，反向配对回其匹配的 '['，字符串/转义感知避免被值内括号误导
    end = t.rfind(']')
    if end < 0:
        return t
    depth = 0
    in_str = False
    start = -1
    j = end
    while j >= 0:
        ch = t[j]
        if ch == '"':
            # 反向扫描下"是否被转义"取决于紧邻前面连续反斜杠的个数，奇数个才是真转义
            k = j - 1
            backslashes = 0
            while k >= 0 and t[k] == '\\':
                backslashes += 1
                k -= 1
            if backslashes % 2 == 0:
                in_str = not in_str
        elif not in_str:
            if ch == ']':
                depth += 1
            elif ch == '[':
                depth -= 1
                if depth == 0:
                    start = j
                    break
        j -= 1
    if start < 0:
        return t
    return t[start:end + 1]


# 定位出的候选片段可能仍带裸引号、缺逗号等格式问题：交给 json_repair 做实际修复。
# 两步分工：定位解决"多段疑似 JSON 选错"，repair 解决"选对的那段内部格式坏了"。
def _strip_code_fence(text:str)->str:
    candidate = _locate_json_candidate(text)
    if not candidate:
        return candidate
    return repair_json(candidate)


class Memory:
    def __init__(self,memory_agent,loop = None):
        # memory agents 相关
        self.memory_agent = memory_agent
        self.loop = loop

        # memory 侧单例收口为实例属性：供注入到 tool 后通过 memory.memory_storage / memory_config / memory_log / memory_prompts 调用，
        # 避免在 tool 侧再开一条直接 import 子包单例的平行读取路径(违反 memory 读取统一收口在 Memory 类内的红线)
        self.memory_storage = memory_storage
        self.memory_config = memory_config
        self.memory_log = memory_log
        self.memory_prompts = memory_prompts

        # memory type 相关
        self.memory_type = memory_config.get_memory_config(file_name='memory_type')


    # memory_agent 后续需要多种场景的处理、输入以及输出，所以需要一个更替prompt的方法适配，避免过多subagent导致冗余
    def _switch_prompt(self,type:str = None,exclude_key:tuple=None):
        # 每次切换模式说明对应场景任务已经完成，清空message_list同时更换system_prompt

        if type == 'memory_type':
            self.memory_agent.message_list = [{'role':'system','content':memory_prompts.get_memory_type_prompt()}]

        if type == 'user_info':
            self.memory_agent.message_list = [{'role':'system','content':memory_prompts.get_user_info_prompt()}]

        if type == 'advanced_task':
            self.memory_agent.message_list = [{'role':'system','content':memory_prompts.get_advanced_task_prompt()}]

        if type == 'normal_task':
            self.memory_agent.message_list = [{'role':'system','content':memory_prompts.get_normal_task_prompt(exclude_key=exclude_key)}]

        if type == 'session_timeline':
            self.memory_agent.message_list = [{'role':'system','content':memory_prompts.get_session_timeline_prompt()}]
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

            # 直接调用分类模型，同时开启 provider 的 reasoning 输出供实时观察；分类结果仍只读取 content。
            # response_format 强制 provider 层输出合法 JSON：本调用不带 tools，是唯一能安全加这个约束的分类入口
            # (已实测 medium_level 模型接受顶层数组 + 该参数，不会拒绝或改写结构)
            response = self.memory_agent.agent_ai.chat.completions.create(
                model=self.memory_agent.model_name,
                messages=input_message,
                extra_body={'thinking': {'type': 'enabled'}},
                response_format={'type': 'json_object'}
            ).choices[0].message
            agent_think = getattr(response, 'reasoning_content', None) or ''
            if agent_think and (not self.loop or self.loop.verbose):
                rich_print(message=agent_think, type='subagent_thinking')
            rq = (response.content or '').strip()

            # 不区分成败记录thinking+原始输出，供后续评估分类质量/优化prompt使用
            memory_log.memory_eval_log(
                stage='slice_type_define',
                slice_data=slice,
                agent_response={'content':response.content,'reasoning_content':agent_think}
            )

            # 剥离可能出现的markdown代码块(与_session_slice_summary的防御性解析保持一致)
            rq = _strip_code_fence(rq)

            # 解析memory_agent回复json
            try:
                rq_json = json.loads(rq)
            except json.JSONDecodeError as error:
                memory_log.memory_log_write(
                    stage='slice_type_define.json_parse_failed',
                    error=error,
                    slice_data=slice,
                    agent_response={
                        'content':response.content,
                        'reasoning_content':agent_think
                    }
                )
                return None

            # 无分类命中([{"result":null}] 或空)时 slice_tag 保持空、跳过特征库更新,
            # 统一走下方 slice_data 构造返回 slice_type=[] 的同构结构--避免原始 slice(无 slice_type、
            # 带 worthy_summary)与 slice_data 混存导致 slice_node 结构不一致;type_name 只能是
            # task/user_info 不会扩展,result:null 即纯聊天,空 slice_type 入库后永不再分类是合理终态
            slice_tag = []
            # LLM 偶尔返回 dict(如 {"result":null})而非 list,归一成 list 再取 [0](防 rq_json[0] KeyError)
            if isinstance(rq_json, dict):
                rq_json = [rq_json]
            # rq_json[0] 是 dict 且不含 'result'(有分类)才处理;list of string 等异常格式跳过
            if rq_json and isinstance(rq_json[0], dict) and 'result' not in rq_json[0]:
                # 存在返回结果，逐个type_name更新特征库(新增/合并)，同时收集本slice的分类标签
                for result in rq_json:
                    if not isinstance(result, dict):
                        continue
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

        # 不区分成败记录thinking+原始输出，供后续评估质量/优化prompt使用
        memory_log.memory_eval_log(stage='user_info_extract',slice_data=slice_data,agent=self.memory_agent)

        rq = _strip_code_fence(rq)

        try:
            rq_json = json.loads(rq)
        except (json.JSONDecodeError,TypeError) as error:
            memory_log.memory_exception_log(
                stage='user_info_extract.json_parse_failed',
                error=error,
                slice_data=slice_data,
                agent=self.memory_agent
            )
            raise

        # 过滤掉没有 info_source 的条目(无来源=不可靠,不入库;符合"只提取有据可依信息"原则)
        for dim in rq_json:
            if 'info_list' in dim:
                dim['info_list'] = [info for info in dim['info_list'] if info.get('info_source')]

        # 将返回结果传回给user.json
        memory_storage.update_memory_storage(file_name='user',file_content=rq_json)

        return rq_json


    # 开始处理user_info_json
    def user_info_reform(self,rq_json):
        # # 本函数说明：处理memory_agent在user_info_extract输出的信息，然后对 memory_config/memory_configs/user_info.json 中的参考模板进行处理
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
        

    # done(@claude): 暂不预支 storage 缓存；当前唯一写入口 advanced_task_updater 已负责持锁读改写，后续接入并发 task 队列时再按实际竞争模型设计缓存。
    # 将 slice 与已有高级任务节点做语义匹配；匹配成功时更新描述并保存来源范围。
    def advanced_task_node_judge(self,slice_data:dict=None,messages:list[dict]=None):
        advanced_task_nodes = memory_storage.get_memory_storage(file_name='advanced_task_node') or []

        # 空库没有候选节点，直接交给未来的新节点合成流程。
        if not advanced_task_nodes:
            return JUDGE_NO_MATCH

        self._switch_prompt(type='advanced_task')
        self.memory_agent.refresh_agent_level(agent_level='medium_level')
        input_message = {
            "slice_topic":slice_data['slice_anchor']['topic'],
            "slice_key_words":slice_data['slice_anchor']['key_words'],
            "slice_summary_detail":slice_data['slice_anchor']['summary_detail'],
            "slice_messages_list":[message for message in messages if slice_data['start_round']<=message['message_round'] <= slice_data['end_round']]
        }
        advanced_rq = self.loop.loop_run(agent=self.memory_agent,message=str(json.dumps(input_message,ensure_ascii=False,indent=2)))

        # 不区分成败记录thinking+原始输出，供后续评估质量/优化prompt使用
        memory_log.memory_eval_log(stage='advanced_task_node_judge',slice_data=slice_data,agent=self.memory_agent)

        # 模型输出不可信：先去除可能的代码块，再按三态契约区分无匹配与失败。
        advanced_rq = _strip_code_fence(advanced_rq)
        try:
            advanced_rq_json = json.loads(advanced_rq)
        except (json.JSONDecodeError, TypeError) as error:
            memory_log.memory_log_write(
                stage='advanced_task_node_judge.json_parse_failed',
                error=error,
                slice_data=slice_data,
                agent=self.memory_agent
            )
            return JUDGE_FAILED
        if advanced_rq_json == [{"result":None}]:
            return JUDGE_NO_MATCH
        if not isinstance(advanced_rq_json,list) or not advanced_rq_json:
            memory_log.memory_log_write(
                stage='advanced_task_node_judge.invalid_response_shape',
                error='模型输出不是非空 JSON 数组',
                slice_data=slice_data,
                agent=self.memory_agent
            )
            return JUDGE_FAILED

        # 模型只能更新已有节点，避免其虚构 task_id 或覆盖其他持久化字段。
        nodes_by_id = {node.get('task_id'):node for node in advanced_task_nodes}
        updates = {}
        for result in advanced_rq_json:
            if not isinstance(result,dict):
                return JUDGE_FAILED
            task_id = result.get('task_id')
            task_desc = result.get('task_desc')
            task_detail = result.get('task_detail')
            if (not isinstance(task_id,int) or isinstance(task_id,bool)
                    or task_id not in nodes_by_id
                    or task_id in updates
                    or not isinstance(task_desc,str) or not task_desc.strip()
                    or not isinstance(task_detail,str) or not task_detail.strip()):
                memory_log.memory_log_write(
                    stage='advanced_task_node_judge.invalid_result_fields',
                    error='task_id/task_desc/task_detail 未满足输出契约',
                    slice_data=slice_data,
                    agent=self.memory_agent
                )
                return JUDGE_FAILED
            updates[task_id] = {'task_desc':task_desc,'task_detail':task_detail}

        slice_ref = {
            'session_id':slice_data['session_id'],
            'time_stamp':slice_data['time_stamp'],
            'start_round':slice_data['start_round'],
            'end_round':slice_data['end_round']
        }

        # 存储层统一负责持锁读改写；当前阶段按一次匹配结果直接落盘。
        advanced_node_results = []
        def _update_advanced_task_nodes(nodes):
            for node in nodes:
                update = updates.get(node.get('task_id'))
                if update is None:
                    continue
                # 已固化 node(skill_info 已写回):只 append 新来源累积进 task_slices_nodes,
                # 不覆写 skill_info/task_desc/task_detail;累积量达阈值时产出"更新"candidate
                if not node.get('skill_info', None):
                    node['task_desc'] = update['task_desc']
                    node['task_detail'] = update['task_detail']
                node['task_slices_nodes'].append(dict(slice_ref))
                sources = node.get('task_slices_nodes', [])
                skill_info = node.get('skill_info')
                # 未固化 node:合并兜底,累积来源达阈值产出"创建"candidate(阈值写 >=2,因未固化 node
                # 新建时已至少带2来源,append后至少3,真实触发点为3,与 normal_task_node_judge 的 >=3 等价)
                # 已固化 node:写回时 task_slices_nodes 清空->从0重新累积,>=3 即新变体真实累积阈值,产出"更新"candidate
                # 来源列表统一 list 拷贝:避免多 slice 合并同一 node 时 candidate 被后续 append 污染
                if not skill_info and len(sources) >= 2:
                    advanced_node_results.append({
                        "task_id": int(node.get('task_id')),
                        "task_desc": node.get('task_desc'),
                        "task_detail": node.get('task_detail'),
                        "task_slices_nodes": list(sources),
                    })
                elif skill_info and len(sources) >= 3:
                    advanced_node_results.append({
                        "task_id": int(node.get('task_id')),
                        "candidate_type": "update",
                        "skill_name": skill_info.get('skill_name'),
                        "skill_desc": skill_info.get('skill_desc'),
                        "task_slices_nodes": list(sources),
                    })
        memory_storage.advanced_task_updater(_update_advanced_task_nodes)
        
        return advanced_node_results if advanced_node_results else JUDGE_MERGED
    

    # 如果advanced task node 没有能合并的，那就排查是否存在普通的task node可以进行合并
    def normal_task_node_judge(self,slice_data:dict=None,messages:list[dict]=None):
        # 候选池筛选权威在 get_normal_task_prompt，此处只传入被判断 slice 自身坐标用于排除自引用
        self.memory_agent.refresh_agent_level(agent_level='medium_level')
        exclude_key = (slice_data['session_id'],slice_data['start_round'],slice_data['end_round'])
        self._switch_prompt(type='normal_task',exclude_key=exclude_key)

        # 拼接输入的message
        input_message = {
            "slice_topic":slice_data['slice_anchor']['topic'],
            "slice_key_words":slice_data['slice_anchor']['key_words'],
            "slice_summary_detail":slice_data['slice_anchor']['summary_detail'],
            "slice_messages_list":[message for message in messages if slice_data['start_round']<=message['message_round'] <= slice_data['end_round']]
        }
        normal_rq = self.loop.loop_run(agent=self.memory_agent,message=str(json.dumps(input_message,ensure_ascii=False,indent=2)))

        # 不区分成败记录thinking+原始输出，供后续评估质量/优化prompt使用
        memory_log.memory_eval_log(stage='normal_task_node_judge',slice_data=slice_data,agent=self.memory_agent)

        # 模型输出不可信：先去代码块，再按三态契约区分无匹配与失败；有匹配时只接受含单个 dict 的数组
        normal_rq = _strip_code_fence(text=normal_rq)
        try:
            normal_rq_json = json.loads(normal_rq)
        except (json.JSONDecodeError, TypeError) as error:
            memory_log.memory_log_write(
                stage='normal_task_node_judge.json_parse_failed',
                error=error,
                slice_data=slice_data,
                agent=self.memory_agent
            )
            return JUDGE_FAILED
        if normal_rq_json == [{"result":None}]:
            return JUDGE_NO_MATCH
        if not isinstance(normal_rq_json,list) or len(normal_rq_json) != 1 or not isinstance(normal_rq_json[0],dict):
            memory_log.memory_log_write(
                stage='normal_task_node_judge.invalid_response_shape',
                error='模型输出不是仅含一个对象的 JSON 数组',
                slice_data=slice_data,
                agent=self.memory_agent
            )
            return JUDGE_FAILED

        result = normal_rq_json[0]
        task_desc = result.get('task_desc')
        task_detail = result.get('task_detail')
        selected_slices = result.get('selected_slices')
        if (not isinstance(task_desc,str) or not task_desc.strip()
                or not isinstance(task_detail,str) or not task_detail.strip()
                or not isinstance(selected_slices,list) or not selected_slices):
            memory_log.memory_log_write(
                stage='normal_task_node_judge.invalid_result_fields',
                error='task_desc/task_detail/selected_slices 未满足输出契约',
                slice_data=slice_data,
                agent=self.memory_agent
            )
            return JUDGE_FAILED

        # 来源回填走红线：模型只给坐标，用 slice_node 核对存在并以真实记录回填，不信模型自吐的 time_stamp
        slice_node = memory_storage.get_memory_storage(file_name='slice_node') or []
        node_index = {
            (node['session_id'],node['start_round'],node['end_round']):node
            for node in slice_node
        }
        # 预置输入 slice 自身坐标：其来源由下方 slice_ref 追加，模型若误选输入 slice 在此被去重丢弃
        input_key = (slice_data['session_id'],slice_data['start_round'],slice_data['end_round'])
        seen = {input_key}
        matched_refs = []
        for sel in selected_slices:
            if not isinstance(sel,dict):
                continue
            key = (sel.get('session_id'),sel.get('start_round'),sel.get('end_round'))
            if key in seen:
                continue
            node = node_index.get(key)
            if node is None:
                continue
            seen.add(key)
            matched_refs.append({
                'session_id':node['session_id'],
                'time_stamp':node['time_stamp'],
                'start_round':node['start_round'],
                'end_round':node['end_round']
            })
        # 模型选的坐标一个都没核对上 → 判失败，不落盘半成品
        if not matched_refs:
            memory_log.memory_log_write(
                stage='normal_task_node_judge.unverified_selected_slices',
                error='selected_slices 未命中 slice_node 中的候选坐标',
                slice_data=slice_data,
                agent=self.memory_agent
            )
            return JUDGE_FAILED

        # 输入 slice 自身来源由 Python 追加（模型不输出它），组成新任务的完整来源
        slice_ref = {
            'session_id':slice_data['session_id'],
            'time_stamp':slice_data['time_stamp'],
            'start_round':slice_data['start_round'],
            'end_round':slice_data['end_round']
        }
        task_slices_nodes = [slice_ref] + matched_refs

        # 落盘：存储层持锁读改写；新 task_id 取整数 id 的 max+1，跳过示例行字符串 id，空库从 1
        # new_task_id 闭包内生成、闭包外消费:candidate 必须带 task_id 交下游 _emit_skill_candidate_attachment
        # (其中硬取 candidate['task_id']),漏带会让 attachment 生成时 KeyError,且因后台钩子静默吞异常而隐蔽
        new_task_id = None
        def _append_new_task_node(nodes):
            nonlocal new_task_id
            int_ids = [n['task_id'] for n in nodes if isinstance(n.get('task_id'),int) and not isinstance(n.get('task_id'),bool)]
            new_task_id = max(int_ids)+1 if int_ids else 1
            nodes.append({
                "task_id":new_task_id,
                "task_desc":task_desc,
                "task_detail":task_detail,
                "task_slices_nodes":task_slices_nodes
            })
        memory_storage.advanced_task_updater(updater=_append_new_task_node)

        # 来源节点大于等于3个 → 返回聚合对象交下游提 skill，否则只算合并成功
        if len(task_slices_nodes) >= 3:
            return [{"task_id":new_task_id,"task_desc":task_desc,"task_detail":task_detail,"task_slices_nodes":task_slices_nodes}]
        else:
            return JUDGE_MERGED


    # 将一个已结束 session 内全部 worthy_summary 的 slice 摘要提炼成一条时间线事件；
    # 走 loop.loop_run(而非 slice_type_define 式的孤立直调)是因为叙事提炼时可能需要
    # memory_agent 主动调用 session_slice 重读某个关键片段的原文，孤立调用拿不到工具。
    # 不落 time_stamp：session_id 本身就带时间信息，不重复存一份容易漂移的派生字段。
    def session_timeline_extract(self,slices:list[dict],session_id:str)->dict|None:
        if not slices:
            return None

        self._switch_prompt(type='session_timeline')
        self.memory_agent.refresh_agent_level(agent_level='medium_level')

        input_info = [
            {
                "session_id":s['session_id'],
                "start_round":s['start_round'],
                "end_round":s['end_round'],
                "topic":s['slice_anchor']['topic'],
                "key_words":s['slice_anchor']['key_words'],
                "summary_detail":s['slice_anchor']['summary_detail'],
            }
            for s in slices
        ]

        rq = self.loop.loop_run(agent=self.memory_agent,message=json.dumps(input_info,ensure_ascii=False,indent=2))

        # 不区分成败记录thinking+原始输出，供后续评估质量/优化prompt使用；无单条slice可关联，只记session_id
        memory_log.memory_eval_log(stage='session_timeline_extract',slice_data={'session_id':session_id},agent=self.memory_agent)

        rq = _strip_code_fence(rq)
        try:
            rq_json = json.loads(rq)
        except (json.JSONDecodeError,TypeError) as error:
            memory_log.memory_log_write(
                stage='session_timeline_extract.json_parse_failed',
                error=error,
                slice_data={'session_id':session_id},
                agent=self.memory_agent
            )
            return self._fallback_timeline_entry(slices=slices,session_id=session_id)
        if not isinstance(rq_json,list) or len(rq_json) != 1 or not isinstance(rq_json[0],dict):
            memory_log.memory_log_write(
                stage='session_timeline_extract.invalid_response_shape',
                error='模型输出不是仅含一个对象的 JSON 数组',
                slice_data={'session_id':session_id},
                agent=self.memory_agent
            )
            return self._fallback_timeline_entry(slices=slices,session_id=session_id)

        result = rq_json[0]
        thread = result.get('thread')
        summary = result.get('summary')
        keywords = result.get('keywords')
        failed_fields = []
        if not isinstance(thread,list) or not thread or not all(isinstance(item,str) and item.strip() for item in thread):
            failed_fields.append('thread')
        if not isinstance(summary,str) or not summary.strip():
            failed_fields.append('summary')
        if not isinstance(keywords,list) or not keywords or not all(isinstance(item,str) and item.strip() for item in keywords):
            failed_fields.append('keywords')
        if failed_fields:
            memory_log.memory_log_write(
                stage='session_timeline_extract.field_validation_failed',
                error=f"字段不合规: {','.join(failed_fields)}",
                slice_data={'session_id':session_id},
                agent=self.memory_agent
            )
            return self._fallback_timeline_entry(slices=slices,session_id=session_id)

        timeline_entry = {
            "session_id":session_id,
            "thread":thread,
            "summary":summary,
            "keywords":keywords,
            "source":"llm",
        }
        memory_storage.timeline_updater(lambda timeline: timeline.append(timeline_entry))

        return timeline_entry


    # session_timeline_extract 在 LLM 提炼失败(JSON 解析失败/响应形状不对/字段校验不合规)时,
    # 用 slice 原始信息降级构造 timeline_entry 写入,避免该 session 在跨会话时间线整段消失--
    # 失败 session 通常有 4-7 个 worthy slice,整段丢失会让 timeline system prompt 注入和 memory_recall
    # 的 session_ids 圈定都漏掉它。thread 直接取各 slice 的 summary_detail(未压缩,语义对齐
    # thread 定义--prompt 里 thread 本就是"逐条压缩 summary_detail",降级即不压缩);summary
    # 留空(降级无概括能力,且 keywords 已覆盖 topic 实体,留 topic 拼接冗余);keywords 聚合
    # 各 slice 的 key_words 去重不截断(保留全部唯一词,扩大 memory_recall 圈 session_ids 候选)。
    # 标记 source='fallback' 便于追溯;消费者 render_timeline_entry(prompt/prompts/timeline_prompt)对空 summary 做容错省略渲染
    def _fallback_timeline_entry(self,slices:list[dict],session_id:str)->dict|None:
        thread = []
        topics = []
        seen = set()
        keywords = []
        for s in slices:
            anchor = s.get('slice_anchor') or {}
            topic = anchor.get('topic')
            if isinstance(topic,str) and topic.strip():
                topics.append(topic.strip())
            detail = anchor.get('summary_detail') or topic
            if isinstance(detail,str) and detail.strip():
                thread.append(detail.strip())
            for kw in anchor.get('key_words',[]) or []:
                if isinstance(kw,str) and kw.strip() and kw not in seen:
                    seen.add(kw)
                    keywords.append(kw)
        if not thread:
            # slice 全无可用 summary_detail/topic,降级也失败:补 log 避免静默(与"防静默"红线一致)
            memory_log.memory_log_write(
                stage='session_timeline_extract.fallback_empty',
                error='slice 全无可用 summary_detail/topic,降级构造失败',
                slice_data={'session_id':session_id},
                agent=self.memory_agent
            )
            return None

        summary = ""

        # key_words 全空时用 topic 兜底,保证 keywords 非空(消费者 '、'.join 空串会输出"关键词:")
        if not keywords:
            keywords = topics

        timeline_entry = {
            "session_id":session_id,
            "thread":thread,
            "summary":summary,
            "keywords":keywords,
            "source":"fallback",
        }
        memory_storage.timeline_updater(lambda timeline: timeline.append(timeline_entry))
        return timeline_entry


    # skill_candidates 的数据形状(task_desc/task_detail/task_slices_nodes)只有本类清楚，
    # 语义化为人话字符串这一步必须在生产者内部完成；attachment 只负责协议措辞与拼接，不解析业务字段
    def _emit_skill_candidate_attachment(self,session,candidate:dict):
        source_count = len(candidate.get('task_slices_nodes',[]))
        task_slices_nodes = candidate.get('task_slices_nodes',[])
        # candidate_type 区分创建/更新:更新 candidate 语义精简(只带 skill_name/skill_desc/新来源),
        # 不带已固化 node 的旧 task_desc(=skill_desc,与 frontmatter 重复)/task_detail(创建前旧值,过时)
        if candidate.get('candidate_type') == 'update':
            content = (
                f"已有技能 {candidate['skill_name']} 最近又累积了 {source_count} 次相似任务的新变体，建议更新该技能以覆盖新变体：\n"
                f"任务id：{candidate['task_id']}\n"
                f"技能名：{candidate['skill_name']}\n"
                f"当前技能描述：{candidate['skill_desc']}\n"
                f"新变体来源坐标（session_id/start_round/end_round）：{json.dumps(task_slices_nodes,ensure_ascii=False)}\n"
                "请调用 ask_user_question 向用户确认是否同意更新该技能；"
                "用户同意后使用 skill_load 加载 create-skill 技能并按其「更新场景」流程执行"
                "（该技能会指导你先 file_read 已有 skill.md 作为基线，再用 session_slice 回溯上述新坐标取得素材，"
                "对比后以 diff 为主向用户展示修订并确认，写盘覆盖、测试，最终调用 skill_finish 完成对该 task_id 节点的写回）。"
            )
        else:
            content = (
                f"最近 {source_count} 次任务被识别为相似模式，建议固化为可复用技能：\n"
                f"任务id：{candidate['task_id']}\n"
                f"任务概述：{candidate['task_desc']}\n"
                f"任务详情：{candidate['task_detail']}\n"
                f"来源坐标（session_id/start_round/end_round）：{json.dumps(task_slices_nodes,ensure_ascii=False)}\n"
                "请调用 ask_user_question 向用户确认是否同意创建该技能；"
                "用户同意后使用 skill_load 加载 create-skill 技能并按其流程执行"
                "（该技能会指导你用 session_slice 回溯上述坐标取得原始素材，起草 skill.md，"
                "经你确认后写盘、测试，最终调用 skill_finish 完成对该 task_id 节点的写回）。"
            )
        session.attachment.attachment_add(
            attachment_type='interrupt',
            attachment_source='memory_pipeline',
            attachment_content=content,
        )

    
    # skill_create 之后写回 advanced_task_node:给对应 task_id 的 node 打 skill_info 标记,
    # task_desc 用 skill_desc 覆盖,task_slices_nodes 搬进 skill_info.skill_source_nodes 后清空。
    # 写回后 advanced_task_node_judge 的 not node.get('skill_info') 为 False,不再重复提示创建技能。
    # 整个读改写在 advanced_task_updater 锁内完成:原实现锁外改 get_memory_storage 的反序列化副本,
    # 一个字节都落不了盘(正是 skill_info_no_writeback bug 的根因)。
    def advanced_nodes_skillInfo(self, task_id: int, skill_name: str = None, skill_desc: str = None) -> bool:
        found = False
        def _writeback(nodes):
            nonlocal found
            for node in nodes:
                nid = node.get('task_id')
                if isinstance(nid, int) and not isinstance(nid, bool) and nid == task_id:
                    # skill_source_nodes 用 append:首次创建取当前 task_slices_nodes;
                    # 后续技能更新再调时,新累积的 task_slices_nodes 追加进已有 skill_source_nodes,不丢旧来源
                    existing_sources = (node.get('skill_info') or {}).get('skill_source_nodes', [])
                    node['skill_info'] = {
                        'skill_name': skill_name,
                        'skill_desc': skill_desc,
                        'skill_source_nodes': existing_sources + node.get('task_slices_nodes', []),
                    }
                    node['task_desc'] = skill_desc
                    node['task_slices_nodes'] = []
                    found = True
                    return
        memory_storage.advanced_task_updater(_writeback)
        return found



    # done(@claude): 修复三处bug——存储存的是分类后结果而非原始切片、遍历范围收窄到本次新片、slice_type字段名与传参修正
    # 方法说明：将切片的分类、存储、按照type分配管道进行统合，方便hook直接对接
    # session 由 hook 逐次调用传入(不进 __init__)：attachment 归属当前 session，slices_pipeline 只在
    # 拿到 skill_candidates 时按需消费，session 为 None(如单测、未来离线批处理)则跳过 attachment 写入
    def slices_pipeline(self,slices:list[dict],messages:list[dict],session=None,enable:bool=True):

        # 控制全局memory_pipeline处理开关，用于静默测试，不改变userinfo或是tasknodes等相关落盘文件信息
        if not enable:
            return

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

        # 进入管线处理逻辑:只对本轮真正新入库、同时进行处理不同type的slice_node，@claude这里后续其实要并行处理的
        # skill_candidates 收集本轮所有 slice 产出的"够格建 skill"节点信息,advanced/normal 结构一致,统一交给上层集中处理
        skill_candidates = []
        for slice in actually_new:
            if 'user_info' in slice.get('slice_type',[]):
                rq_json = self.user_info_extract(slice_data=slice,messages=messages)
                self.user_info_reform(rq_json=rq_json)

            if 'task' in slice.get('slice_type',[]):
                judge_result = self.advanced_task_node_judge(slice_data=slice,messages=messages)
                # 三态契约:FAILED 直接放弃该slice的task处理;NO_MATCH 才进normal
                if judge_result == JUDGE_NO_MATCH:
                    judge_result = self.normal_task_node_judge(slice_data=slice,messages=messages)
                # 排除三种JUDGE态,剩下的就是skill-worthy节点列表
                if judge_result not in (JUDGE_MERGED,JUDGE_FAILED,JUDGE_NO_MATCH):
                    skill_candidates.extend(judge_result)

        # 语义化并交付 attachment：session 为 None 时跳过，不影响 slice/user_info/task 的既有落盘
        if session is not None:
            for candidate in skill_candidates:
                self._emit_skill_candidate_attachment(session,candidate)
        

        
