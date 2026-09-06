import json
import threading

from datetime import datetime

from config import TRACE_ENABLE,TRACE_LOG_FILE_PATH


class Trace:

    _current = None
    _pending_lines = []
    _pending_lock = threading.Lock()

    def __init__(self,trace_id):

        self.trace_id = trace_id
        self.trace_file_path = None
        self.trace_file_lock = threading.Lock()
        self.trace_error_list = []
        self._trace_start()

        if TRACE_ENABLE:
            Trace._current=self

    def _trace_start(self):
        # 如果没有开启trace，不进行后续动作
        if not TRACE_ENABLE:
            return
        
        # 进行下一步动作之前，确认trace_log_file根目录存在
        TRACE_LOG_FILE_PATH.mkdir(parents=True,exist_ok=True)
        self.trace_file_path=TRACE_LOG_FILE_PATH/f"{self.trace_id}.jsonl"
        self.trace_file_path.touch(exist_ok=True)

        # 处理未创建trace之前pending进去的trace_lines
        self._absorb_pending()


    @classmethod
    def trace_record(cls,trace_type:str,loop_round:str='',stream_key:str='',source:str='',trace_detail:dict=None):
        if not TRACE_ENABLE:
            return

        if trace_detail is None:
            trace_detail = {}

        trace_line = {
            # 精度到微秒：工具执行常在1秒内，秒级时间戳相减直接归零
            "time_stamp":datetime.now().strftime('%Y%m%d_%H%M%S_%f'),
            "trace_type":trace_type,
            "source":source,
            "loop_round":loop_round,
            "stream_key":stream_key,
            "trace_detail":trace_detail if isinstance(trace_detail,dict) else {"detail_dict_trans":str(trace_detail)}
        }

        if cls._current is None:
            with cls._pending_lock:
                cls._pending_lines.append(trace_line)
                return

        else:
            cls._current._trace_file_write(trace_line)


    def _trace_file_write(self,trace_line):
        try:
            trace_text = json.dumps(trace_line,ensure_ascii=False,default=str)
        except Exception as ee:
            trace_line_fallback = {
                key:trace_line.get(key) for key in (
                    "time_stamp","trace_type","source","loop_round","stream_key"
                )
            }
            trace_line_fallback["trace_detail"] = {"trace_error":f"{type(ee).__name__} : {ee}"}
            trace_text = json.dumps(trace_line_fallback,ensure_ascii=False,default=str)
            
        with self.trace_file_lock:
            try:
                with open(self.trace_file_path,"a",encoding='utf-8') as trace_file:
                    trace_file.write(trace_text + "\n")
            except Exception as ee:
                self.trace_error_list.append({
                    "trace_file_write_error":f"{type(ee).__name__} : {ee}",
                    "trace_line":trace_text
                })

    def _absorb_pending(self):
        with Trace._pending_lock:
            for trace_line in Trace._pending_lines:
                self._trace_file_write(trace_line=trace_line)
            Trace._pending_lines.clear()

    @classmethod
    def trace_end(cls):
        if not TRACE_ENABLE or not Trace._current:
            return
        cls.trace_record(
            trace_type='trace_end',
            source='system',
            trace_detail={"trace_error_list":cls._current.trace_error_list}
        )