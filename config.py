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
# session 对话最大token值
MAX_SESSION_TOKEN = 300000


# memory config
MEMORY_STORAGE_PATH = Path(__file__).parent/'memory'/'memory_storage'/'memory_storages'



# loacal model
LOCAL_MODEL_PATH = Path(__file__).parent/'local_model'
LOCAL_EMBEDDING_MODEL = Path(__file__).parent/'local_model/iic/nlp_gte_sentence-embedding_chinese-base'