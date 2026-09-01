import json
import threading

from datetime import datetime

# 进行eval之前，建立trace的生命周期跟踪，通过hook注入的方式，进行整体的生命周期跟踪，记录关键事件和状态变化，便于调试和分析。
# eval数据追踪项：系统输入、用户输入、模型思考、模型输出、模型消费、工具输入参数、工具输出结果、工具执行时间
class Trace:

    # 初始化建立trace日志文件路径和session对象，便于在整个生命周期中记录关键事件和状态,同时尽可能服用当前已经存在但是分散的数据记录
    # 突然的想法，实际上按照出发点来记录就行，比如user_input、tool_call、tool_result、assistant_think、assistant_content之类的
    def __init__(self,trace_id:str,trace_enable,trace_log_file_path):
        self.trace_enable = trace_enable

        self.trace_id = trace_id
        self.trace_log_file_path = trace_log_file_path
        self.trace_file_lock = threading.Lock() # 异步track hook文件读写锁 
        self.trace_error_list = []

        self.trace_file_path = self._generate_trace_file() if self.trace_log_file_path and self.trace_enable else None
        self.trace_start()

    # 初始化trace_file_path，只保证文件存在不写内容
    # 用touch不用write_text：后者无条件覆盖，同秒重启或重复构造会清空已有记录
    def _generate_trace_file(self):
        # 确保trace_log_file存在
        self.trace_log_file_path.mkdir(parents=True,exist_ok=True)

        trace_file_path = self.trace_log_file_path/f"{self.trace_id}.jsonl"
        trace_file_path.touch(exist_ok=True)
        return trace_file_path


    # 文件带锁追加防异步并行hooktrace文件写入
    # 'a'模式打开不截断且每次写入前定位到文件末尾，等于追加一行，不碰已有内容
    # 追加而非整读整写：trace是高频事件流，读全文改再覆盖是O(n²)，且覆盖写一旦中断毁的是整个文件
    # default=str 兜底 usage / ChatCompletionMessage 这类非JSON原生对象，宁可退化成字符串也不丢整行
    def _trace_append(self,trace_line:dict):
        # @claude 这里观察一下，是否存在各种eval需要的过程报错emit，如果需要的话构造的时候将tui_core的emit方法传进来
        # 序列化失败(循环引用 / __str__自身抛)：文件还是好的，降级写占位，不让这条从时间线上消失
        try:
            trace_text = json.dumps(trace_line,ensure_ascii=False,default=str)
        except Exception as ee:
            # 骨架五项全由trace_record构造，类型只有str/int；毒只可能在trace_detail里。
            # fallback必须排除trace_detail——放进来就是拿同一份毒再序列化一次，兜底自己就成了崩溃点
            trace_line_fallback = {
                key:trace_line.get(key) for key in (
                    "time_stamp","trace_type","source","loop_round","stream_key"
                )
            }
            trace_line_fallback["trace_detail"] = {"trace_error":f"{type(ee).__name__} : {ee}"}
            trace_text = json.dumps(trace_line_fallback,ensure_ascii=False,default=str)

        # 落盘失败(磁盘满 / 路径被删 / 权限)：连占位都写不进去，只能在内存记账，交trace_end自报
        with self.trace_file_lock:
            try:
                # trace_text已经是JSON字符串，直接写；再dumps一次会把整行转义成一个JSON字符串，连换行都没了
                with open(self.trace_file_path,'a',encoding='utf-8') as trace_file:
                    trace_file.write(trace_text + '\n')
            except Exception as ee:
                # 不print：TUI运行期打屏会冲乱Textual界面
                self.trace_error_list.append({
                    "trace_file_error":f"{type(ee).__name__} : {ee}",
                    "trace_text":trace_text
                })

    # 唯一trace_file写入，trace对外暴露唯一写入方法
    # 本函数签名即事件契约，全部hook对着它写；trace_start/trace_end是会话级事件没有轮次和流，故除trace_type外都带默认值
    # source与trace_type正交：trace_type记「发生了什么」，source记「谁产生的」，值域 system/user/attachment/tool/各agent名
    # source一律答「谁发起的」：工具事件填发起调用的agent_name而不是tool，因为trace_type已经说了是工具调用，再填tool是同一件事说两遍
    # 工具记录不带stream_key，靠trace_detail里的tool_call_id对回assistant_output的assistant_toolcalls
    def trace_record(self,trace_type:str,loop_round:str='',stream_key:str='',source:str='',trace_detail:dict=None):
        # 先判断是否存在对应的trace_file，如果没有说明config中的文件位置配置失效，或者没有启用trace
        if not self.trace_file_path or not self.trace_enable:
            return

        if trace_detail is None:
            trace_detail = {}

        # 字段顺序按人眼扫读排：时间→是什么事件→谁→在哪→载荷；trace_id不落行内，文件名即归属
        trace_line = {
            # 精度到微秒：工具执行常在1秒内，秒级时间戳相减直接归零
            "time_stamp":datetime.now().strftime('%Y%m%d_%H%M%S_%f'),
            "trace_type":trace_type,
            "source":source,
            "loop_round":loop_round,
            "stream_key":stream_key,
            "trace_detail":trace_detail if isinstance(trace_detail,dict) else {"detail_dict_trans":str(trace_detail)}
        }

        self._trace_append(trace_line=trace_line)


    # 初始化后落入trace_start类型记录
    def trace_start(self):
        self.trace_record(trace_type="trace_start",source="system")

    # 没有这一行即代表进程非正常退出，缺失本身就是观测结果
    def trace_end(self):
        self.trace_record(
            trace_type='trace_end',
            source='system',
            trace_detail={"trace_error_list":self.trace_error_list}
        )








