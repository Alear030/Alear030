import json

from dataclasses import dataclass

from config import SESSION_PLAN_FILE_PATH

@dataclass
class Plan_step:
    step_number:int = None
    description:str = None
    acceptance_criteria:str = None
    status:str = None
    result:str = None

class Plan:

    # Plan 基础信息
    def __init__(self,plan_file):
        self.plan_file_name = plan_file
        # 得到plan文件内的信息
        self.plan_json = self._get_plan_detail(plan_file=plan_file)

        # 得到plan的基础信息
        self.plan_title = self.plan_json['plan_title']
        self.plan_status = self.plan_json['plan_status']
        self.created_time = self.plan_json['created_time']
        self.update_time = self.plan_json['update_time']
        self.output_file = self.plan_json.get('output_file')
        self.plan_steps = self._get_steps()

        # plan的执行过程信息
        self.first_step = self._get_first_step()

        # 卡控用：本轮 plan_loop 允许更新的唯一 step_number
        # 只由 loop_core._plan_loop 在拿到 first_step 时写入，_refresh() 故意不清空它
        # 目的：防止 agent 跳步更新，或者在同一轮里把后面几个 step 一起标 done
        self.active_step_number = None


    # 从磁盘重新加载 plan 状态（plan_update 后调用）
    def _refresh(self):
        self.plan_json = self._get_plan_detail(plan_file=self.plan_file_name)
        self.plan_status = self.plan_json['plan_status']
        self.update_time = self.plan_json['update_time']
        self.output_file = self.plan_json.get('output_file')
        self.plan_steps = self._get_steps()
        self.first_step = self._get_first_step()


    # 取出plan_file内容
    # for claudecode - 增加json类型防护，修改完删除此行备注
    def _get_plan_detail(self,plan_file):
        plan_path = SESSION_PLAN_FILE_PATH/f'{plan_file}.json'
        plan_json = json.loads(plan_path.read_text(encoding='utf-8'))
        return plan_json
    
    # 得到全部的steps
    def _get_steps(self)->list[Plan_step]:
        steps = []
        for step in self.plan_json['plan_steps']:
            steps.append(Plan_step(
                step_number=step['step_number'],
                description=step.get('description'),
                acceptance_criteria=step.get('acceptance_criteria'),
                status=step.get('status'),
                result=step.get('result')
            ))
        return steps

    
    def _get_first_step(self):
        for step in self.plan_steps:
            if step.status != 'done':
                return step
        return None
        
    
    
