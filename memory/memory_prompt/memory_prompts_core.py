import json

from pathlib import Path


from memory.memory_config.memory_config_core import memory_config
from memory.memory_storage.memory_storage_core import memory_storage

PROMPTS_FILE = Path(__file__).parent/'prompts'


class Memory_prompts:
    def __init__(self):
        pass


    # 分类阶段只需用户画像维度的名称与描述；具体特征仍由提取阶段完整使用。
    def get_memory_type_prompt(self):
        memory_type_json = memory_config.get_memory_config(file_name='memory_type')
        user_info_json = memory_config.get_memory_config(file_name='user_info')
        # dimension_name/dimension_desc 命名区别于顶层分类标签的 type_name，防止模型把画像子维度误当成并列的顶层分类
        user_info_routing_json = [
            {
                'dimension_name': entry['type_name'],
                'dimension_desc': entry['type_desc'],
            }
            for entry in user_info_json
        ]

        memory_type_md_file = PROMPTS_FILE/'memory_type.md'
        memory_type_md_content = memory_type_md_file.read_text(encoding='utf-8').strip()
        memory_type_md_content = memory_type_md_content.replace(
            "{{MEMORY_TYPE_JSON}}", json.dumps(memory_type_json,ensure_ascii=False,indent=2)
        )

        return memory_type_md_content.replace(
            "{{USER_INFO_ROUTING_JSON}}", json.dumps(user_info_routing_json,ensure_ascii=False,indent=2)
        )
    

    # 得到prompts下 user_info pormpt
    def get_user_info_prompt(self):
        user_info_json = memory_config.get_memory_config(file_name='user_info')
        user_json = memory_storage.get_memory_storage(file_name='user')

        user_info_md_file = PROMPTS_FILE/'user_info.md'
        user_info_md_content = user_info_md_file.read_text(encoding='utf-8').strip()

        user_info_md_content = user_info_md_content.replace("{{USER_INFO_JSON}}",json.dumps(user_info_json,ensure_ascii=False,indent=2))
        user_info_md_content = user_info_md_content.replace("{{USER_JSON}}",json.dumps(user_json,ensure_ascii=False,indent=2))

        return user_info_md_content

    def get_advanced_task_prompt(self):
        advanced_task_json = memory_storage.get_memory_storage(file_name='advanced_task_node') or []

        advanced_task_md_file = PROMPTS_FILE/'advance_task.md'
        advanced_task_md_content = advanced_task_md_file.read_text(encoding='utf-8').strip()

        return advanced_task_md_content.replace("{{ADVANCED_TASK_JSON}}",json.dumps(advanced_task_json,ensure_ascii=False,indent=2))

    def get_normal_task_prompt(self,exclude_key:tuple=None):
        advanced_task_json = memory_storage.get_memory_storage(file_name='advanced_task_node') or []
        slice_node = memory_storage.get_memory_storage(file_name='slice_node') or []

        # 收集已被 advanced_task_node 引用的 slice 坐标，候选池要排除它们（已归入高级任务的切片不再游离）
        referenced = {
            (ref['session_id'],ref['start_round'],ref['end_round'])
            for node in advanced_task_json
            for ref in node.get('task_slices_nodes',[])
        }

        # 候选池 = task 类型、未被任何 advanced_task_node 引用、且不是本次输入 slice 自身的游离切片；
        # exclude_key 排除自引用：调用方判断该 slice 时，该 slice 可能已先被写入 slice_node，
        # 不排除会导致候选池把"正在被判断的输入 slice"也当作候选之一。每条精简成 7 字段供模型判断
        normal_task_json = [
            {
                "session_id":node['session_id'],
                "time_stamp":node['time_stamp'],
                "start_round":node['start_round'],
                "end_round":node['end_round'],
                "topic":node['slice_anchor']['topic'],
                "key_words":node['slice_anchor']['key_words'],
                "summary_detail":node['slice_anchor']['summary_detail']
            }
            for node in slice_node
            if 'task' in node.get('slice_type',[])
            and (node['session_id'],node['start_round'],node['end_round']) not in referenced
            and (node['session_id'],node['start_round'],node['end_round']) != exclude_key
        ]

        normal_task_md_file = PROMPTS_FILE/'normal_task.md'
        normal_task_md_content = normal_task_md_file.read_text(encoding='utf-8').strip()

        return normal_task_md_content.replace("{{NORMAL_TASK_JSON}}",json.dumps(normal_task_json,ensure_ascii=False,indent=2))

    # session_timeline 无占位符需要替换，是纯静态 system_prompt
    def get_session_timeline_prompt(self):
        session_timeline_md_file = PROMPTS_FILE/'session_timeline.md'
        return session_timeline_md_file.read_text(encoding='utf-8').strip()


memory_prompts = Memory_prompts()