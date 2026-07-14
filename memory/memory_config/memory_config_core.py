import json

from pathlib import Path


memory_configs_path = Path(__file__).parent/'memory_configs'


class Memory_config:
    def __init__(self):
        pass
    

    # @claude(ignore) - 兼容当前的memory_config_update方法，用于config文件的json读写锁住
    def _json_update(self,updater):
        # json文件锁进行并行异步管控
        with self.json_lock:
            # 1-读取json内容 2-用updater func 处理data 3-写回json内容
            data = json.loads(self.session_path.read_text(encoding='utf-8'))
            updater(data)
            self.session_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

    
    def get_memory_config(self,file_name):
        file_path = memory_configs_path/f'{file_name}.json'
        if file_path.exists():
            file_json = json.loads(file_path.read_text(encoding='utf-8').strip())
            if file_json is not None:
                return file_json
            else:
                return None
            
    # done(@claude): 方法名已改为update_memory_config(定义+memory_core.py两处调用同步)
    def update_memory_config(self,file_name,file_content):
        file_path = memory_configs_path/f'{file_name}.json'
        file_path.write_text(
            json.dumps(file_content,ensure_ascii=False,indent=2),
            encoding='utf-8'
        )
            

memory_config = Memory_config()