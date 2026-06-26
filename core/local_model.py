from modelscope import snapshot_download
from pathlib import Path
# from config import LOCAL_MODEL_PATH


model_dir = snapshot_download(
    "iic/nlp_gte_sentence-embedding_chinese-base",
    cache_dir=Path(__file__).parent.parent/'local_model'
)