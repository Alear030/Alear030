import json
import tiktoken
import threading

from datetime import datetime
from pathlib import Path
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor,as_completed

from config import SESSION_MEMORTY_DETAIL_PATH,MAX_SESSION_TOKEN
from local_model import _get_embedding_model,embedding_to_b64
from .session_plan import Plan
from .attachment_core import Attachment

def _json_read(file_path:Path):
    if file_path.is_dir():
        return
    file_text = file_path.read_text(encoding='utf-8')

    if not file_text.strip():
        return []
    
    file_json = json.loads(file_text)
    return file_json


def _json_write(content:str=None,file_path:Path=None):
    if file_path.is_dir():
        print('system error target file is dir')
        return

    if not content:
        print('null content is none can not write in a json file')
        return

    # session_detail/ 已 gitignore 且无占位文件,全新 clone 上并不存在;
    # 上面的 is_dir() 对不存在的路径返回 False 不拦,故此处必须建目录,否则首次启动写 session 即 FileNotFoundError
    file_path.parent.mkdir(parents=True,exist_ok=True)
    file_path.write_text(
        json.dumps(content,ensure_ascii=False,indent=2),
        encoding='utf-8'
    )


# 统一从 message_list 元素取文本:dict({'role','content'}) 取 content;OpenAI assistant message
# 对象取 .content,其 tool_calls 若非空单独成 JSON 计入(函数名/参数占 token,不可忽略)。
# 供 _session_count_tokens 遍历混合类型的 message_list 用
def _msg_text(msg) -> str:
    if isinstance(msg, dict):
        content = msg.get('content')
        return content if isinstance(content, str) else ''
    text = getattr(msg, 'content', None) or ''
    tool_calls = getattr(msg, 'tool_calls', None)
    if tool_calls:
        text += json.dumps([tc.model_dump() for tc in tool_calls], ensure_ascii=False)
    return text


class Session:
    
    def __init__(self,slice_agent,summary_agent,system_prompt:str):
        # session class 基础信息
        self.session_id = self._generate_session_id()
        self.round = 1
        self.mode = 'auto'#后续需要和tool get相关 plan mode 需要禁止一切的写操作
        self.max_tokens = MAX_SESSION_TOKEN
        self.system_prompt = system_prompt
        self.session_path = self._generate_session_json()

        # session subagent 信息
        self.slice_agent = slice_agent

        self.summary_agent = summary_agent

        # session 读写锁
        self.json_lock = threading.Lock()

        # session 状态控制
        self.mode = 'auto'#后续需要和tool get相关 plan mode 需要禁止一切的写操作
        
        # session_plan 类
        self.plan:Plan = None

        # attachment：当前 session 内、仅供 main agent 本轮消费的运行时提示；纯内存态，不持久化
        self.attachment = Attachment()


    def _json_update(self,updater):
        # json文件锁进行并行异步管控
        with self.json_lock:
            # 1-读取json内容 2-用updater func 处理data 3-写回json内容
            data = json.loads(self.session_path.read_text(encoding='utf-8'))
            updater(data)
            self.session_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


    def _generate_session_id(self):
        time_now = datetime.now()
        time_part = time_now.strftime('%Y%m%d_%H%M%S')
        return time_part
    

    def _generate_session_json(self):

        session_json_detail = {
            "session_id":self.session_id,
            # "unslice_pointer":0,
            "session_slice":[],
            "session_messages":[{
                "message_round": 0,
                "message_role": "system",
                "message_content": str(self.system_prompt)
            }]
        }
        _json_write(content=session_json_detail,file_path=SESSION_MEMORTY_DETAIL_PATH/f'{self.session_id}.json')
        return SESSION_MEMORTY_DETAIL_PATH/f'{self.session_id}.json'
    
    
    def _session_count_tokens(self, agent) -> int:
        # 算 main agent 的 message_list 全量 token--这才是模型实际看到、且 compress 会缩小的量,
        # 计数才能在 compress 后下降、不重复触发。原实现读 session_messages 且只算"最后一片 + system",
        # 而 message_list 持续累积全部历史(loop_core._sent_message_api 每轮 append、无每轮重构),
        # 导致计数严重低估、compress 几乎不可能触发--这是 compress 不触发的真正根因,比阈值大更根本。
        # message_list 元素是混合类型:dict({'role','content'}) 与 OpenAI assistant message 对象
        # (.content/.tool_calls),用 _msg_text 统一取文本
        token_count = 0
        token_encoding = tiktoken.encoding_for_model(model_name='gpt-4o')
        for msg in agent.message_list:
            token_count += 4  # per-message 开销,与原实现一致
            text = _msg_text(msg)
            if text:
                token_count += len(token_encoding.encode(text))
        return token_count
    
    
    def _session_slice(self):
        def do_slice(data):
            # 处理slice的基础数据
            session_slice = data['session_slice']
            session_messages = [m for m in data['session_messages'] if m['message_role'] != 'system']
            # 指针取最后一片的 start_round：最后一片是「未封口的临时尾巴」，重喂它是为了让新轮次
            # 有机会并进同一片（同一件事继续），而不是每来一轮就封一片
            slice_pointer = session_slice[-1]['start_round'] if session_slice else int(0)

            # 得到没有slice的messages（重喂窗口 = round >= 指针，天然含最后那片的轮次；
            # 保留 tool_calls/tool_result：工具调用是对话中真实发生的动作，是切片 agent 判断任务型
            # 片段边界、以及下游消费端提炼 task/工作流的关键依据，不能在切片阶段丢弃）
            unslice_messages = []
            for msg in session_messages:
                if msg['message_round'] >= slice_pointer:
                    unslice_messages.append(msg)

            if not unslice_messages:
                return

            # 处理slice subagent 的message list
            message_list = []
            message_list.append(self.slice_agent.message_list[0])
            message_list.append({'role':'user','content':json.dumps(unslice_messages,ensure_ascii=False,indent=2)})

            # 开始slice 并对sessionjson的session_slice进行覆盖
            slice_rqs = self.slice_agent.agent_ai.chat.completions.create(model=self.slice_agent.model_name,messages = message_list).choices[0].message.content
            try:
                # 剥离可能的 markdown 代码块（与 summary 处一致，防止模型裹 ```json 导致解析崩溃）
                import re
                cleaned = slice_rqs.strip()
                m = re.match(r'^```(?:json)?\s*\n(.*?)\n```\s*$', cleaned, re.DOTALL)
                if m:
                    cleaned = m.group(1).strip()
                parsed_slices = json.loads(cleaned)
                if not parsed_slices:
                    return

                # 按窗口真实起点归一化，不信任模型回显的绝对 round：模型时常把重喂窗口当成一段新对话
                # 从 1 重新编号，导致 start_round 与真实轮次错位、合并时对不齐而堆积重复片。取窗口内消息
                # 的真实最小 round 作锚点，用「锚点 - 模型首片 start」的偏移把整批拉回真实编号——模型守
                # 规矩输出绝对 round 时 offset=0 原样通过；重编号时 offset 把它映射回去。
                window_start = min(msg['message_round'] for msg in unslice_messages)
                window_end = max(msg['message_round'] for msg in unslice_messages)
                offset = window_start - parsed_slices[0]['start_round']
                for s in parsed_slices:
                    s['start_round'] += offset
                    s['end_round'] += offset

                # 校验归一化后无缝、无重叠、恰好覆盖整个窗口（提示词已强制模型连续覆盖）；
                # 不满足说明模型输出结构坏了，跟解析失败一样跳过本轮，不写脏数据
                expect = window_start
                for s in parsed_slices:
                    if s['start_round'] != expect or s['end_round'] < s['start_round']:
                        raise ValueError('slice 轮次不连续')
                    expect = s['end_round'] + 1
                if expect - 1 != window_end:
                    raise ValueError('slice 未覆盖到窗口末尾')

                # 构造归一化后的新切片批次
                new_slices = []
                for slice in parsed_slices:
                    slice_text = f"{slice['topic']} {' '.join(slice['key_words'])}"
                    slice_embedding = _get_embedding_model().encode([slice_text])[0]# @claude 后续这里坐上了memory类，需要移除，保证收口，保证处理速度效率
                    new_slices.append({
                        "worthy_summary":slice['worthy_summary'],
                        "session_id":self.session_id,
                        "time_stamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
                        "start_round": slice['start_round'],
                        "end_round": slice['end_round'],
                        "slice_embedding": embedding_to_b64(slice_embedding),
                        "slice_anchor":{
                            "topic": slice['topic'],
                            "key_words": slice['key_words'],
                            "summary_detail":""
                        }
                    })

                # 砍尾重接：丢弃所有 start_round >= 指针的旧片（即被重喂的最后那片，尾巴长大后
                # 可能裂成多片），再整体接上归一化后的新批次。取代旧的「只跟 [-1] 单条对账」——
                # 模型重编号时对不齐会漏判成 append 产生重复。
                kept = [s for s in session_slice if s['start_round'] < slice_pointer]
                data['session_slice'] = kept + new_slices
            except (json.JSONDecodeError,IndexError,KeyError,ValueError):
                print('slice json 存在问题 跳过本轮 slice')

        self._json_update(updater=do_slice)
        
    
    def _session_slice_summary(self,session_slice:dict,session_messages:list)->dict:
        #判断是否需要进行summary
        if not session_slice['worthy_summary'] or session_slice['slice_anchor']['summary_detail']:
            return session_slice
        
        #取到需要进行summary的messages
        summary_messages = []
        for msg in session_messages:
            if msg['message_round'] >= session_slice['start_round'] and msg['message_round'] <= session_slice['end_round']:
                if msg['message_role'] == 'user' or msg['message_role'] == 'assistant':
                    summary_messages.append(msg)
        
        #处理summary subagent 的message list 并得到结果
        message_list = []
        message_list.append(self.summary_agent.message_list[0])
        message_list.append({'role':'user','content':json.dumps(summary_messages,ensure_ascii=False)})
        summary_rqs = self.summary_agent.agent_ai.chat.completions.create(model=self.summary_agent.model_name,messages=message_list).choices[0].message.content
        try:
            # 剥离可能的 markdown 代码块
            import re
            cleaned = summary_rqs.strip()
            m = re.match(r'^```(?:json)?\s*\n(.*?)\n```\s*$', cleaned, re.DOTALL)
            if m:
                cleaned = m.group(1).strip()
            summary_json = json.loads(cleaned)
            summary_result = summary_json[0]['summary_detail']
        except (json.JSONDecodeError,IndexError,KeyError):
            summary_result = summary_rqs
        
        # 处理session_slice的summary
        session_slice['slice_anchor']['summary_detail'] = summary_result

        # 更新slice的embedding
        slice_text = f"{session_slice['slice_anchor']['topic']} {' '.join(session_slice['slice_anchor']['key_words'])} {session_slice['slice_anchor']['summary_detail']}"
        slice_embedding = _get_embedding_model().encode([slice_text])[0]
        session_slice['slice_embedding'] = embedding_to_b64(slice_embedding)

        return session_slice


    def _session_summary(self):
        def do_summary(data):
        # 得到session的slice 和 session的session_messages
            session_messages = data['session_messages']
            session_slices = data['session_slice']

            # 创建多线程处理需要summary的slice
            with ThreadPoolExecutor(max_workers=5) as tp:
                # 创建summary队列
                slice_summary_queue = {
                    tp.submit(self._session_slice_summary,slice,session_messages):slice for slice in session_slices
                }

                # 取得summary队列的返回结果
                slices_results = []
                for thread in as_completed(slice_summary_queue):
                    result = thread.result()
                    slices_results.append(result)
                
            # 对得到的slices_results 进行排序
            slices_results.sort(key=lambda x:x['start_round'])

            # 对session json 进行复写并覆盖
            data['session_slice'] = slices_results

        self._json_update(updater=do_summary)


    def session_message_reform(self):
        session_json = _json_read(file_path=self.session_path)
        messages = []
        
        # 得到system_prompt
        if session_json['session_messages'][0]['message_role'] == 'system':
            messages.append(session_json['session_messages'][0])

        # 得到最后一个slice的messages
        session_last_slice = session_json['session_slice'][-1]
        for msg in session_json['session_messages']:
            if msg['message_round'] >= session_last_slice['start_round'] and msg['message_round'] <= session_last_slice['end_round']:
                messages.append(msg)

        # 将messages转化成message_list
        message_list =[]
        for msg in messages:
            if msg['message_role'] in ['system','user','assistant']:
                message_list.append({'role':msg['message_role'],'content':msg['message_content']})
            elif msg['message_role'] == 'tool_calls':
                message_list[-1]['tool_calls'] = json.loads(msg['message_content'])
            else:
                message_list.append(json.loads(msg['message_content']))
        
        return message_list


    def _build_compress_attachment(self, session_slices: list) -> str:
        # 构造 compress 时注入的 slice summary 字符串。B 版:每片输出 topic + summary_detail,
        # 让 agent 在压缩后仍能回溯当前 session 更早片段的内容(更早原始消息已从上下文移除,
        # 而 memory_recall 排除当前 session 救不回来,故必须经 attachment 自动注入)。
        # 最后一片不在此列--它的原始消息保留在 message_list 中,无需 summary
        lines = []
        for slice in session_slices:
            anchor = slice['slice_anchor']
            lines.append(
                f"session{slice['session_id']} 片段(round {slice['start_round']}-{slice['end_round']}):"
                f"主题 {anchor['topic']}。详情: {anchor.get('summary_detail') or '(无摘要)'}"
            )
        return "以下是本次会话已压缩掉的更早片段摘要(原始消息已从上下文移除,如需细节用 session_slice 工具按坐标回读):\n" + '\n\n'.join(lines)


    def session_compress(self, agent):
        # 压缩:token 超阈值时,把更早 slice 的 summary 经 attachment 注入(解决失忆),message_list 重置为
        # system + 最后一片原始消息(保留当前任务连续)。下一轮 _sent_message_api 把 attachment 拼入并清空
        if self._session_count_tokens(agent) >= self.max_tokens:
            # 兜底:对没 summary_detail 的片补跑(_session_slice_summary 内置守卫跳过已摘要);
            # memory_pipeline 每轮后台已产 summary,通常空跑,仅防 memory_pipeline 未跑完的时序缺口
            self._session_summary()
            session_json = _json_read(file_path=self.session_path)
            session_slices = session_json['session_slice']
            # 除最后一片外,注入当前 session 的 slice summary(最后一片的原始消息保留在 message_list)
            if len(session_slices) > 1:
                self.attachment.attachment_add(
                    attachment_type='notification',
                    attachment_source='session_compress',
                    attachment_content=self._build_compress_attachment(session_slices[:-1])
                )
            # 清空历史,保留 system + 最后一片原始消息(复用 session_message_reform,不改它)
            agent.message_list = self.session_message_reform()
        

    def session_message_insert(self,role,content):

        def do_insert(data):
            # 在session json中的session_messages插入新的message
            data['session_messages'].append({
                "message_round": self.round,
                "message_role": str(role),
                "message_content":str(content)
            })
            # 将新的sessionjson写回文件
        
        self._json_update(updater=do_insert)


# plan 函数方法集群
    # 初始化session中的plan类，并将当前session进入plan模式用于后续loop使用
    def _plan_init(self,plan_file):
        self.plan = Plan(plan_file=plan_file)
        self.mode = 'plan'

