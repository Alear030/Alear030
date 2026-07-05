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

def _json_read(file_path:Path):
    if file_path.is_dir():
        # rich_print(message='error:path is dir',type='system_error')
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
    
    file_path.write_text(
        json.dumps(content,ensure_ascii=False,indent=2),
        encoding='utf-8'
    )


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
    
    
    def _session_count_tokens(self)->int:
        session_json = _json_read(file_path=self.session_path)
        count_pointer = session_json['session_slice'][-1]['start_round'] if session_json['session_slice'] else int(0)
        
        #处理需要计算tokens的message list
        count_messages = []
        #将需要计数的messages取出
        for msg in session_json['session_messages']:
            if msg['message_round'] >= count_pointer or msg['message_role'] == 'system':
                count_messages.append(msg['message_content'])
        
        #开始计算
        token_count = 0
        token_encoding = tiktoken.encoding_for_model(model_name='gpt-4o')
        for msg in count_messages:
            token_count+=4
            token_count += len(token_encoding.encode(msg))
        
        return token_count
    
    
    def _session_slice(self):
        def do_slice(data):
            # 处理slice的基础数据
            session_slice = data['session_slice']
            session_messages = [m for m in data['session_messages'] if m['message_role'] != 'system']
            slice_pointer = session_slice[-1]['start_round'] if session_slice else int(0)
            
            # 得到没有slice的messages（保留 tool_calls/tool_result：工具调用是对话中真实发生的动作，
            # 是切片 agent 判断任务型片段边界、以及下游消费端提炼 task/工作流的关键依据，不能在切片阶段丢弃）
            unslice_messages = []
            for msg in session_messages:
                if msg['message_round'] >= slice_pointer:
                    unslice_messages.append(msg)

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
                for slice in json.loads(cleaned):
                    # 添加embedding数据
                    slice_text = f"{slice['topic']} {' '.join(slice['key_words'])}"
                    slice_embedding = _get_embedding_model().encode([slice_text])[0]# @claude 后续这里坐上了memory类，需要移除，保证收口，保证处理速度效率
                    slice_data = {
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
                    }
                    # 判断当前slice是否存在数据
                    if not session_slice:
                        session_slice = [slice_data]
                    # 判断新的切片的起始round和最后切片的round是否一样
                    elif session_slice[-1]['start_round'] == slice_data['start_round']:
                        session_slice[-1] = slice_data
                    else:
                        session_slice.append(slice_data)

                data['session_slice'] = session_slice
            except (json.JSONDecodeError,IndexError,KeyError):
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


    def session_compress(self,agent):
        # 判断是否需要进行压缩，如果需要进行压缩则将mainagent的messagelist进行重构
        if self._session_count_tokens() >= self.max_tokens:
            self._session_summary()
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

