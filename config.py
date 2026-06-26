from pathlib import Path



ROOT_DIRECTORY = Path(__file__).parent
WORK_SPACE = Path(__file__).parent/'workspace'

# agent config 
MAX_TOOLCALLS = int(15)

# main_MODEL_NAME="deepseek-v4-pro"
# slice_MODEL_NAME="deepseek-v4-flash"
# summary_MODEL_NAME="deepseek-v4-flash"
# subagent_MODEL_NAME='deepseek-v4-flash'


#session config
SESSION_SUMMARY_PATH = Path(__file__).parent/'session/session_summary.json'
SESSION_MEMORTY_DETAIL_PATH = Path(__file__).parent/'session/session_detail'

MAX_SESSION_TOKEN = 300000


# loacal model
LOCAL_MODEL_PATH = Path(__file__).parent/'local_model'
LOCAL_EMBEDDING_MODEL = Path(__file__).parent/'local_model/iic/nlp_gte_sentence-embedding_chinese-base'