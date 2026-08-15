import copy
import json
import re
import tiktoken
import threading

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from openai.types.chat import ChatCompletionMessage
from concurrent.futures import ThreadPoolExecutor,as_completed

from config import (
    SESSION_MEMORTY_DETAIL_PATH,
    MAX_SESSION_TOKEN,
    STRUCTURED_API_TIMEOUT,
    STRUCTURED_API_RETRIES,
    SLICE_TOOL_RESULT_MAX_CHARS,
)
from local_model import _get_embedding_model,embedding_to_b64
from .session_plan import Plan
from .attachment_core import Attachment


# 当前上下文 token 用量的内存态缓存,供 TUI 状态栏展示;不写 session JSON。
# used 由 _session_count_tokens 写入(与 compress 同源),max_tokens 对齐 Session.max_tokens。
@dataclass
class ContextTokens:
    used: int = 0
    max_tokens: int = 0


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


# slice/summary 的结构化抽取直调:固定关 thinking 并收紧 timeout/重试。
# 这两个调用不走 Loop._chat(不带 tools,也不需要思维链),开着 thinking 时长响应会在网关侧被
# 掐断成 APIConnectionError,叠加客户端默认重试后单次切片可阻塞数分钟(见 config 常量处实测数据)。
def _structured_chat(agent,message_list:list)->str:
    client = agent.agent_ai.with_options(timeout=STRUCTURED_API_TIMEOUT,max_retries=STRUCTURED_API_RETRIES)
    response = client.chat.completions.create(
        model=agent.model_name,
        messages=message_list,
        extra_body={'thinking':{'type':'disabled'}},
    )
    return response.choices[0].message.content or ''


# 剥离模型可能裹上的 markdown 代码块,让下游 json.loads 拿到裸 JSON
def _strip_code_fence(text:str)->str:
    cleaned = (text or '').strip()
    fenced = re.match(r'^```(?:json)?\s*\n(.*?)\n```\s*$',cleaned,re.DOTALL)
    return fenced.group(1).strip() if fenced else cleaned


# 切片重喂窗口的载荷:只截断超长 tool_result 正文,其余消息原样传。
# tool_calls 消息(工具名 + 参数)不截断——切片 agent 判断任务型片段边界靠的是它,
# 而 tool_result 的完整正文对边界判断没有增量价值,却能把窗口顶到几万 token。
def _slice_window_payload(messages:list)->list:
    payload = []
    for msg in messages:
        content = msg.get('message_content') or ''
        if msg.get('message_role') == 'tool_result' and len(content) > SLICE_TOOL_RESULT_MAX_CHARS:
            trimmed = dict(msg)
            trimmed['message_content'] = (
                content[:SLICE_TOOL_RESULT_MAX_CHARS]
                + f'...[tool_result 已截断,原长 {len(content)} 字符]'
            )
            payload.append(trimmed)
        else:
            payload.append(msg)
    return payload


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

        # 上下文 token 用量缓存(内存态);启动与每轮 after_round/compress 时由 _session_count_tokens 刷新
        self.context_tokens = ContextTokens(max_tokens=self.max_tokens)


    def _json_update(self,updater):
        # json文件锁进行并行异步管控
        # updater 里只允许做纯内存改写:锁被持有期间任何写 session 的调用(尤其 session_message_insert
        # 写用户输入)都要排队,把 LLM/embedding 放进来会让用户输入几分钟落不了盘
        with self.json_lock:
            # 1-读取json内容 2-用updater func 处理data 3-写回json内容
            data = json.loads(self.session_path.read_text(encoding='utf-8'))
            updater(data)
            self.session_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


    def _json_snapshot(self)->dict:
        # 锁内只读取一份快照,供锁外的慢计算(LLM/embedding)使用;结果由后续短锁写回
        with self.json_lock:
            return json.loads(self.session_path.read_text(encoding='utf-8'))


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
        # 同步写入展示缓存,让 TUI 与 compress 读到同一数值
        self.context_tokens.used = token_count
        return token_count
    
    
    def _session_slice(self):
        # 三段式:锁内读快照 → 锁外跑 LLM/embedding → 锁内短写。慢计算不能留在锁里,
        # 否则用户输入的 session_message_insert 要等整轮切片结束才落盘。
        data = self._json_snapshot()

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

        # 处理slice subagent 的message list（超长 tool_result 正文在此截断，见 _slice_window_payload）
        message_list = []
        message_list.append(self.slice_agent.message_list[0])
        message_list.append({
            'role':'user',
            'content':json.dumps(_slice_window_payload(unslice_messages),ensure_ascii=False,indent=2)
        })

        # 锁外调用切片模型：失败只放弃本轮切片（下一轮重喂窗口会把这批消息再带上），并让用户可见
        try:
            slice_rqs = _structured_chat(agent=self.slice_agent,message_list=message_list)
        except Exception as error:
            #@agent 后续兼容到LOGGING模块中，统一管理日志打印
            return

        try:
            # 剥离可能的 markdown 代码块（与 summary 处一致，防止模型裹 ```json 导致解析崩溃）
            parsed_slices = json.loads(_strip_code_fence(slice_rqs))
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
        except (json.JSONDecodeError,IndexError,KeyError,ValueError,TypeError) as error:
            #@agent 后续兼容到LOGGING模块中，统一管理日志打印
            return
        except Exception as error:
            # embedding 加载/编码失败等:同样只放弃本轮切片,但必须上报——否则异常冒泡到后台
            # future 里,既看不见,还会连带跳过同一个 hook 里紧随其后的 _session_summary
            #@agent 后续兼容到LOGGING模块中，统一管理日志打印
            return

        def do_slice(data):
            # 开口式写回：定型前缀必写；若盘上在前缀之后已覆盖得比本次窗口更远，则保留那段后续，
            # 不因尾片变更整批丢弃（否则定型片进不了 memory_pipeline，重喂窗口会堆积）
            current_slice = data['session_slice']
            sealed = new_slices[:-1] if len(new_slices) > 1 else []
            open_slice = new_slices[-1]
            write_window_end = open_slice['end_round']
            sealed_end = sealed[-1]['end_round'] if sealed else slice_pointer - 1

            kept = [s for s in current_slice if s['start_round'] < slice_pointer]
            continuation = [s for s in current_slice if s['start_round'] > sealed_end]
            continuation_end = max((s['end_round'] for s in continuation), default=-1)

            if continuation_end > write_window_end:
                # 盘上后续更远：前缀落地，尾部用盘上的（sealed 为空时即只留盘上，不拿旧开口回滚）
                data['session_slice'] = kept + sealed + continuation
            else:
                # 常规开口更新：砍掉指针及之后的旧片，接上本批（含新开口尾）
                data['session_slice'] = kept + new_slices

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
        summary_rqs = _structured_chat(agent=self.summary_agent,message_list=message_list)
        try:
            # 剥离可能的 markdown 代码块
            summary_json = json.loads(_strip_code_fence(summary_rqs))
            summary_result = summary_json[0]['summary_detail']
        except (json.JSONDecodeError,IndexError,KeyError,TypeError):
            summary_result = summary_rqs
        
        # 处理session_slice的summary
        session_slice['slice_anchor']['summary_detail'] = summary_result

        # 更新slice的embedding
        slice_text = f"{session_slice['slice_anchor']['topic']} {' '.join(session_slice['slice_anchor']['key_words'])} {session_slice['slice_anchor']['summary_detail']}"
        slice_embedding = _get_embedding_model().encode([slice_text])[0]
        session_slice['slice_embedding'] = embedding_to_b64(slice_embedding)

        return session_slice


    def _session_summary(self):
        # 与 _session_slice 同构:锁内读快照 → 锁外并行跑 summary → 锁内按坐标合并
        data = self._json_snapshot()

        # 得到session的slice 和 session的session_messages
        session_messages = data['session_messages']
        session_slices = data['session_slice']

        # 只挑真正缺 summary 的片进队列(原实现把全部片都 submit,靠 _session_slice_summary 内部守卫空跑)。
        # 判据以 _session_slice_summary 里的守卫为准,这里只是提前过滤掉不需要排队的片
        pending_slices = [
            slice for slice in session_slices
            if slice['worthy_summary'] and not slice['slice_anchor']['summary_detail']
        ]
        if not pending_slices:
            return

        # 锁外多线程处理需要summary的slice;传副本,避免锁外改到快照里的对象
        summarized = {}
        with ThreadPoolExecutor(max_workers=5) as tp:
            # 创建summary队列:future → 该片的轮次坐标,写回时按坐标对账
            slice_summary_queue = {
                tp.submit(self._session_slice_summary,copy.deepcopy(slice),session_messages):
                    (slice['start_round'],slice['end_round'])
                for slice in pending_slices
            }

            # 取得summary队列的返回结果;单片失败不拖垮整批,下一轮会再补
            for thread in as_completed(slice_summary_queue):
                slice_key = slice_summary_queue[thread]
                try:
                    summarized[slice_key] = thread.result()
                except Exception as error:
                    #@agent 后续兼容到LOGGING模块中，统一管理日志打印
                    pass

        if not summarized:
            return

        def do_summary(data):
            # 按 (start_round,end_round) 逐片合并,不整表覆盖:锁外这段时间里 session_slice 可能已被
            # 切片改过(尾片裂开/重接),整表回写会把那些改动抹掉。
            # 切片顺序由 _session_slice 的「kept + new_slices」保证(原实现在此处重排序),此处只改字段不动顺序
            for slice in data['session_slice']:
                result = summarized.get((slice['start_round'],slice['end_round']))
                if not result or slice['slice_anchor']['summary_detail']:
                    continue
                # 空摘要不落盘:模型返回空内容时连同那份按空摘要算出的 embedding 一起丢弃,
                # 留给下一轮重试,避免用劣化向量覆盖切片阶段算出的可用 embedding
                summary_detail = result['slice_anchor']['summary_detail']
                if not (summary_detail or '').strip():
                    continue
                slice['slice_anchor']['summary_detail'] = summary_detail
                slice['slice_embedding'] = result['slice_embedding']

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
        # 按 role 分类落盘：assistant 收到 ChatCompletionMessage 对象时正文/thinking 分离成键，
        # 有 tool_calls 再追加一条 tool_calls 消息；其余 role 收字符串原样写。字段结构收口在本类，
        # loop 侧只交对象/字符串，不感知 session JSON 形状。
        def do_insert(data):
            if role == 'assistant' and isinstance(content, ChatCompletionMessage):
                msg = {
                    "message_round": self.round,
                    "message_role": "assistant",
                    "message_content": content.content or '',
                }
                thinking = getattr(content, 'reasoning_content', None)
                if thinking:
                    msg = {
                        "message_round": self.round,
                        "message_role": "assistant",
                        "message_thinking": str(thinking),
                        "message_content": content.content or ''
                    }
                data['session_messages'].append(msg)
                if content.tool_calls:
                    data['session_messages'].append({
                        "message_round": self.round,
                        "message_role": "tool_calls",
                        "message_content": json.dumps(
                            [tc.model_dump() for tc in content.tool_calls], ensure_ascii=False),
                    })
            else:
                data['session_messages'].append({
                    "message_round": self.round,
                    "message_role": str(role),
                    "message_content": '' if content is None else str(content),
                })

        self._json_update(updater=do_insert)


# plan 函数方法集群
    # 初始化session中的plan类，并将当前session进入plan模式用于后续loop使用
    def _plan_init(self,plan_file):
        self.plan = Plan(plan_file=plan_file)
        self.mode = 'plan'

