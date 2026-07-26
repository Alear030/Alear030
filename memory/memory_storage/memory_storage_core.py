import json
import threading

from pathlib import Path


# memory_storages/ 已 gitignore 且无占位文件,全新 clone 上并不存在;
# 下面各处 write_text 都不建目录,故在模块导入时统一建好,避免首次写入时 FileNotFoundError
storages_path = Path(__file__).parent/'memory_storages'
storages_path.mkdir(parents=True,exist_ok=True)

class Memory_storage:
    def __init__(self):
        # storages文件地址：
        self.slice_nodes_path = storages_path/'slice_node.json'
        self.advanced_task_node_path = storages_path/'advanced_task_node.json'
        self.timeline_path = storages_path/'timeline.json'
        self.loker = threading.Lock()


    def get_memory_storage(slef,file_name):
        file_path = storages_path/f'{file_name}.json'
        if file_path.exists():
            file_json = json.loads(file_path.read_text(encoding='utf-8').strip())
            if file_json is not None:
                return file_json
            else:
                return None
            
    # @claude(ignore)当前user_info.json缺少文件读写锁，可能造成覆盖问题
    def update_memory_storage(self,file_name,file_content):
        file_path = storages_path/f'{file_name}.json'
        file_path.write_text(
            json.dumps(file_content,ensure_ascii=False,indent=2),
            encoding='utf-8'
        )


    # json文件读写锁：带锁的原子读改写，避免并发丢更新
    def slice_node_updater(self,updater):
        with self.loker:
            if self.slice_nodes_path.exists():
                raw = self.slice_nodes_path.read_text(encoding='utf-8').strip()
                data = json.loads(raw) if raw else []
            else:
                data = []
            updater(data)
            self.slice_nodes_path.write_text(
                json.dumps(data,ensure_ascii=False,indent=2),
                encoding='utf-8'
            )

    def advanced_task_updater(self,updater):
        with self.loker:
            if self.advanced_task_node_path.exists():
                raw = self.advanced_task_node_path.read_text(encoding='utf-8').strip()
                data = json.loads(raw) if raw else []
            else:
                data = []
            updater(data)
            self.advanced_task_node_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


    def timeline_updater(self,updater):
        with self.loker:
            if self.timeline_path.exists():
                raw = self.timeline_path.read_text(encoding='utf-8').strip()
                data = json.loads(raw) if raw else []
            else:
                data = []
            updater(data)
            self.timeline_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


memory_storage = Memory_storage()