import json
import threading

from datetime import datetime

from config import LOG_ENABLE, LOG_DATA_PATH


# 进程级诊断日志：记构造期、异常路径等系统故障信息，与 eval/trace 的会话事件流互补
# trace 跟 session 记「运行发生了什么」，log 跟进程记「系统哪里出了问题」
# 文件名 = session_id(log_id)，与 trace_log/<session_id>.jsonl 并排，文件名即归属
# enable 与落盘路径由本模块从 config 读取，构造方只需给出 log_id
class Log:

    # 类级状态：pending 缓冲与当前实例。构造期(agents 在 import 期构造)Log 尚未诞生，
    # pending_record 的行先攒在类属性里，首个 Log 落地时自动吸收
    pending_lines = []
    _pending_lock = threading.Lock()
    _current = None

    def __init__(self,log_id:str):
        self.log_id = log_id
        self.log_enable = LOG_ENABLE
        self.log_data_path = LOG_DATA_PATH
        self.log_file_lock = threading.Lock() # 带锁追加防并发写坏行
        self.log_error_list = []

        self.log_file_path = self._generate_log_file() if self.log_data_path and self.log_enable else None
        # enable=False 不接管 pending：后续 pending_record 仍走 stdout 兜底分支
        if self.log_enable:
            Log._current = self
        self._absorb_pending()

    # 初始化log_file_path，只保证文件存在不写内容
    # 用touch不用write_text：后者无条件覆盖，同秒重启或重复构造会清空已有记录
    def _generate_log_file(self):
        self.log_data_path.mkdir(parents=True,exist_ok=True)

        log_file_path = self.log_data_path/f"{self.log_id}.jsonl"
        log_file_path.touch(exist_ok=True)
        return log_file_path

    # Log 落地即吸收构造期攒下的行——渗透语义：写 log 的代码无需知道 log 何时就绪
    def _absorb_pending(self):
        with Log._pending_lock:
            waiting = Log.pending_lines[:]
            Log.pending_lines.clear()
        for line in waiting:
            self._log_append(log_line=line)

    # 所有想写 log 的代码的统一入口,log 是否就绪对调用方透明：
    # 当前实例在 → 等价 log_record；不在 → stdout 一条兜底(构造期 TUI 未起,打屏可见) + 攒行等 Log 吸收
    # pending 行保留攒行时刻的时间戳,不因补写失真
    @classmethod
    def pending_record(cls,level:str,source:str,event:str,detail:dict=None):
        if cls._current is not None:
            cls._current.log_record(level=level,source=source,event=event,detail=detail)
            return

        print(f"[log_pending] {level} {source}:{event}")
        if not LOG_ENABLE:
            return

        # 字段顺序与 log_record 的行结构一致,吸收落盘后两种来源的行不可区分
        line = {
            "time_stamp":datetime.now().strftime('%Y%m%d_%H%M%S_%f'),
            "level":level,
            "source":source,
            "event":event,
            "detail":detail if isinstance(detail,dict) else {"detail_dict_trans":str(detail)}
        }
        with cls._pending_lock:
            cls.pending_lines.append(line)

    # 文件带锁追加
    # default=str 兜底 detail 里的非JSON原生对象，宁可退化成字符串也不丢整行
    # 序列化失败降级写占位；落盘失败(磁盘满/路径被删/权限)连占位都写不进，只能内存记账
    # 日志系统自身绝不能成为新的崩溃源，一切异常不上抛
    def _log_append(self,log_line:dict):
        try:
            log_text = json.dumps(log_line,ensure_ascii=False,default=str)
        except Exception as ee:
            # 骨架五项全由调用方构造，类型只有str/int；毒只可能在detail里
            # fallback必须排除detail——放进来就是拿同一份毒再序列化一次，兜底自己就成了崩溃点
            log_line_fallback = {
                key:log_line.get(key) for key in (
                    "time_stamp","level","source","event"
                )
            }
            log_line_fallback["detail"] = {"log_error":f"{type(ee).__name__} : {ee}"}
            log_text = json.dumps(log_line_fallback,ensure_ascii=False,default=str)

        with self.log_file_lock:
            try:
                # log_text已经是JSON字符串，直接写；再dumps一次会把整行转义成一个JSON字符串
                with open(self.log_file_path,'a',encoding='utf-8') as log_file:
                    log_file.write(log_text + '\n')
            except Exception as ee:
                # 不print：TUI运行期打屏会冲乱Textual界面
                self.log_error_list.append({
                    "log_file_error":f"{type(ee).__name__} : {ee}",
                    "log_text":log_text
                })

    # 唯一log_file写入，log对外暴露唯一写入方法
    # 本函数签名即事件契约；level答「多严重」，source答「谁产生的」，event答「发生了什么」
    def log_record(self,level:str,source:str,event:str,detail:dict=None):
        # 没有log_file说明config中的路径配置失效，或者没有启用log
        if not self.log_file_path or not self.log_enable:
            return

        if detail is None:
            detail = {}

        # 字段顺序按人眼扫读排：时间→多严重→谁→发生了什么→载荷；log_id不落行内，文件名即归属
        log_line = {
            "time_stamp":datetime.now().strftime('%Y%m%d_%H%M%S_%f'),
            "level":level,
            "source":source,
            "event":event,
            "detail":detail if isinstance(detail,dict) else {"detail_dict_trans":str(detail)}
        }

        self._log_append(log_line=log_line)
