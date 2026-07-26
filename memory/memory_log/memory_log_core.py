import json
import threading
import traceback

from datetime import datetime
from pathlib import Path


# 记录 memory 管线的失败诊断与正常评估两类日志。
# 日志可能含真实会话内容，memory_logs 不进版本控制。
memory_logs_path = Path(__file__).parent/'memory_logs'

# 是否把 agent 的最终输出与 thinking 写进日志。默认关闭：这两项是唯一含真实会话内容的字段，
# 对外分发时不应默认落盘；关闭后仍保留 stage/slice_ref/error/traceback，足以定位是哪一片在哪个阶段失败。
# 本地排查静默丢片或评估 prompt 质量时手动置 True。
LOG_AGENT_RESPONSE = False


class Memory_log:
    def __init__(self):
        self.memory_pipeline_log_path = memory_logs_path/'memory_pipeline.jsonl'
        self.memory_pipeline_eval_log_path = memory_logs_path/'memory_pipeline_eval.jsonl'
        self.loker = threading.Lock()


    def _agent_response(self,agent):
        if agent is None or not agent.message_list:
            return None

        message = agent.message_list[-1]
        if isinstance(message,dict):
            return {
                'content':message.get('content'),
                'reasoning_content':message.get('reasoning_content')
            }

        return {
            'content':getattr(message,'content',None),
            'reasoning_content':getattr(message,'reasoning_content',None)
        }


    # 两类日志共用的条目构造：time_stamp/stage(标明来源的memory subagent处理阶段)/slice_ref/agent_response
    def _build_log_entry(self,stage:str,slice_data:dict|None=None,agent=None,agent_response:dict|None=None)->dict:
        log = {
            'time_stamp':datetime.now().astimezone().isoformat(timespec='seconds'),
            'stage':stage
        }

        if slice_data is not None:
            log['slice_ref'] = {
                'session_id':slice_data.get('session_id'),
                'start_round':slice_data.get('start_round'),
                'end_round':slice_data.get('end_round')
            }

        if LOG_AGENT_RESPONSE:
            response = agent_response if agent_response is not None else self._agent_response(agent)
            if response is not None:
                log['agent_response'] = response

        return log


    def _write_log(self,path:Path,log:dict):
        try:
            memory_logs_path.mkdir(parents=True,exist_ok=True)
            with self.loker:
                with path.open('a',encoding='utf-8') as file:
                    file.write(json.dumps(log,ensure_ascii=False)+'\n')
        except Exception:
            pass


    # 日志写入失败不得反过来影响 memory 管线。
    def memory_log_write(self,stage:str,error:Exception|str,slice_data:dict|None=None,agent=None,agent_response:dict|None=None,traceback_info:str|None=None):
        log = self._build_log_entry(stage=stage,slice_data=slice_data,agent=agent,agent_response=agent_response)
        log['error'] = str(error)
        if traceback_info is not None:
            log['traceback'] = traceback_info

        self._write_log(self.memory_pipeline_log_path,log)


    def memory_exception_log(self,stage:str,error:Exception,slice_data:dict|None=None,agent=None,agent_response:dict|None=None):
        self.memory_log_write(
            stage=stage,
            error=error,
            slice_data=slice_data,
            agent=agent,
            agent_response=agent_response,
            traceback_info=traceback.format_exc()
        )


    # 不区分成败，记录每次memory subagent产出的thinking+原始输出，供后续评估质量/优化prompt使用；
    # 与memory_log_write分开落盘，因两者消费场景不同(排错 vs 评估)，混一起后续筛选麻烦。
    def memory_eval_log(self,stage:str,slice_data:dict|None=None,agent=None,agent_response:dict|None=None):
        log = self._build_log_entry(stage=stage,slice_data=slice_data,agent=agent,agent_response=agent_response)
        self._write_log(self.memory_pipeline_eval_log_path,log)


memory_log = Memory_log()
