import json

from pathlib import Path


from memory.memory_config.memory_config_core import memory_config
from memory.memory_storage.memory_storage_core import memory_storage

PROMPTS_FILE = Path(__file__).parent/'prompts'


class Memory_prompts:
    def __init__(self):
        pass


    # 得到prompts下memory_type prompt
    def get_memory_type_prompt(self):
        memory_type_json = memory_config.get_memory_config(file_name='memory_type')

        memory_type_md_file = PROMPTS_FILE/'memory_type.md'
        memory_type_md_content = memory_type_md_file.read_text(encoding='utf-8').strip()

        return memory_type_md_content.replace("{{MEMORY_TYPE_JSON}}",json.dumps(memory_type_json,ensure_ascii=False,indent=2))
    

    # 得到prompts下 user_info pormpt
    def get_user_info_prompt(self):
        user_info_json = memory_config.get_memory_config(file_name='user_info')
        user_json = memory_storage.get_memory_storage(file_name='user')

        user_info_md_file = PROMPTS_FILE/'user_info.md'
        user_info_md_content = user_info_md_file.read_text(encoding='utf-8').strip()

        user_info_md_content = user_info_md_content.replace("{{USER_INFO_JSON}}",json.dumps(user_info_json,ensure_ascii=False,indent=2))
        user_info_md_content = user_info_md_content.replace("{{USER_JSON}}",json.dumps(user_json,ensure_ascii=False,indent=2))

        return user_info_md_content

memory_prompts = Memory_prompts()