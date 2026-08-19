import os

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


ROOT_DIRECTORY = Path(__file__).parent
WORK_SPACE = Path(__file__).parent/'workspace'

# agent_max_tool_call config
MAX_TOOLCALLS = int(30)
SUB_MAX_TOOLCALLS = int(15)

# plan 编排无进展熔断:连续这么多轮拿到同一 step(没推进)就退出
PLAN_STALL_LIMIT = int(3)

# agent_model config
MODEL_LEVEL = {
    "max_level":{
        "base_url":os.getenv('MAX_LEVEL_BASE_URL'),
        "api_key":os.getenv('MAX_LEVEL_API_KEY'),
        "model_name":os.getenv('MAX_LEVEL_MODEL_NAME')
    },
    "medium_level":{
        "base_url":os.getenv('MEDIUM_LEVEL_BASE_URL'),
        "api_key":os.getenv('MEDIUM_LEVEL_API_KEY'),
        "model_name":os.getenv('MEDIUM_LEVEL_MODEL_NAME')
    },
    "low_level":{
        "base_url":os.getenv('LOW_LEVEL_BASE_URL'),
        "api_key":os.getenv('LOW_LEVEL_API_KEY'),
        "model_name":os.getenv('LOW_LEVEL_MODEL_NAME')
    }
}


#session config

# session 对话详情文件夹路径
SESSION_MEMORTY_DETAIL_PATH = Path(__file__).parent/'session/session_detail'
# session plan文件夹路径
SESSION_PLAN_FILE_PATH = Path(__file__).parent/'session/session_plan'
# slice/summary 这类结构化抽取直调的调用边界:
# 实测同一份 4.2k tokens 的切片请求,开着 thinking 时挂 61s 后被网关掐断
# (Server disconnected without sending a response),关掉后 6.5s 正常返回。
# 故这两个直调固定关 thinking,并用下面的 timeout/重试把单次故障的代价限死:
# 关掉 thinking 后正常 6.5s 完成,60s 已是 9 倍余量,再重试只是让后台线程多占一分钟。
# 当前只有 session 的 slice/summary 直调遵守这组边界;memory_core.slice_type_define 是同一类
# 不带 tools 的结构化直调,仍开着 thinking 与客户端默认重试,尚未收进来。
STRUCTURED_API_TIMEOUT = 60
STRUCTURED_API_RETRIES = 0
# 切片重喂窗口里单条 tool_result 的最大字符数:超长工具结果(实测单条 174KB,整个窗口 131k token)
# 会把窗口顶到几万 token,拖慢切片且无助于判断边界——工具名与参数在未截断的 tool_calls 消息里
SLICE_TOOL_RESULT_MAX_CHARS = 2000

# session 对话最大token值:compress 触发阈值,按模型实际上下文窗口留安全余量
# (原 300000 几乎不触发;真正根因是 _session_count_tokens 已修正为算 message_list 全量,
# 此阈值按当前模型窗口保留安全余量设为 250000)
MAX_SESSION_TOKEN = 250000


# memory config
# 跨会话记忆管线的总闸。默认关闭——注意它关掉的不只是"入库":
# memory_pipeline hook 的判空在 session._session_slice() 之前,所以关闭时
# 切片、摘要、slice 分类、user_info 画像、task 节点、timeline 全都不会发生。
# 想体验完整的记忆能力就改成 True(会对每轮对话额外产生若干次模型调用)。
MEMORY_PIPELINE_ENABLED = False

MEMORY_STORAGE_PATH = Path(__file__).parent/'memory'/'memory_storage'/'memory_storages'


# mcp config
# MCP server 配置文件:包名与目录都不能叫 mcp——仓库根即 sys.path[0],会遮蔽已安装的 mcp pip 包
MCP_CONFIG_PATH = Path(__file__).parent/'mcp_client'/'mcp.json'
# 单条 MCP 工具结果的最大字符数:远端工具的返回不受本项目控制(网页正文、大 JSON 都可能整块回来),
# 与 SLICE_TOOL_RESULT_MAX_CHARS 同类取舍——超出部分对模型判断的边际价值低,却会实打实顶爆 session token
MCP_TOOL_RESULT_MAX_CHARS = 4000



# loacal model
LOCAL_MODEL_PATH = Path(__file__).parent/'local_model'
LOCAL_EMBEDDING_MODEL = Path(__file__).parent/'local_model/iic/nlp_gte_sentence-embedding_chinese-base'
# 权重不进版本控制,缺失时按此 id 从 ModelScope 自动下载到 LOCAL_MODEL_PATH(下载后路径即 LOCAL_EMBEDDING_MODEL)
MODELSCOPE_EMBEDDING_ID = 'iic/nlp_gte_sentence-embedding_chinese-base'