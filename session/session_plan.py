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

        # 卡控用：本轮允许被 plan_update 更新的唯一 step_number，由 advance() 写入
        # 目的：防止 agent 跳步更新，或在同一轮里把后面几个 step 一起标 done
        self.active_step_number = None


    # 刷新磁盘状态，锁定并返回下一个待执行 step，全部完成返回 None
    def advance(self)->'Plan_step':
        self._refresh()
        step = self.first_step
        if step is not None:
            self.active_step_number = step.step_number
        return step


    # 从磁盘重新加载 plan 状态（plan_update 后调用）
    def _refresh(self):
        self.plan_json = self._get_plan_detail(plan_file=self.plan_file_name)
        self.plan_status = self.plan_json['plan_status']
        self.update_time = self.plan_json['update_time']
        self.output_file = self.plan_json.get('output_file')
        self.plan_steps = self._get_steps()
        self.first_step = self._get_first_step()


    # 取出plan_file内容，读取或解析失败抛出带文件名的清晰错误
    def _get_plan_detail(self,plan_file):
        plan_path = SESSION_PLAN_FILE_PATH/f'{plan_file}.json'
        try:
            return json.loads(plan_path.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError) as e:
            raise ValueError(f'plan 文件读取/解析失败: {plan_path} — {e}') from e
    
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
        
    
    
