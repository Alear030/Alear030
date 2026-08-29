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

    
    # 首次运行时真身不存在：从随仓库分发的同名 .example.json 播种一份再读。
    # 真身已存在时绝不覆盖——它承载运行时长出来的维度与特征，覆盖等于把用户积累清零。
    def get_memory_config(self,file_name):
        file_path = memory_configs_path/f'{file_name}.json'
        if not file_path.exists():
            example_path = memory_configs_path/f'{file_name}.example.json'
            if not example_path.exists():
                raise FileNotFoundError(
                    f'memory config 缺失且无种子可播：{file_path} 与 {example_path} 都不存在'
                )
            file_path.write_text(example_path.read_text(encoding='utf-8'),encoding='utf-8')

        file_json = json.loads(file_path.read_text(encoding='utf-8').strip())
        # 早前这里读不到就隐式返回 None，调用方拿 None 去迭代，在后台 memory 线程里才炸成
        # TypeError，堆栈离真正的原因很远。就地抛错，把问题钉在配置这一层。
        if file_json is None:
            raise ValueError(f'memory config 内容为 null：{file_path}')
        return file_json
            
    # done(@claude): 方法名已改为update_memory_config(定义+memory_core.py两处调用同步)
    def update_memory_config(self,file_name,file_content):
        file_path = memory_configs_path/f'{file_name}.json'
        file_path.write_text(
            json.dumps(file_content,ensure_ascii=False,indent=2),
            encoding='utf-8'
        )
            

memory_config = Memory_config()