from config import PLAN_STALL_LIMIT


# Plan 分步编排器：拥有 plan 多轮控制流，逐个 step 驱动 Loop 执行
# 未来 GoalRunner 可在外层包住 run()：检查产出→不合格重新 plan→再跑，无需改 Loop
class PlanRunner:

    def __init__(self,loop,session):
        self.loop = loop
        self.session = session

    # 编排入口：非 plan 模式直接空返回，决策收在此处，main 无条件调用即可
    def run(self,agent)->str:
        if not self.session or self.session.mode != 'plan' or not self.session.plan:
            return None

        # 逐个 step 驱动，无进展熔断：连续 PLAN_STALL_LIMIT 轮拿到同一 step 就退出
        last_step_number = None
        stall = 0
        last_result = ''
        while True:
            if not self.session.plan:
                break
            step = self.session.plan.advance()
            if step is None:
                break

            # 同一 step 连续出现说明没被标 done，累计到上限则熔断
            if step.step_number == last_step_number:
                stall += 1
                if stall >= PLAN_STALL_LIMIT:
                    break
            else:
                stall = 0
                last_step_number = step.step_number

            last_result = self.loop.run_turn(agent=agent,message=self._build_step_prompt(step))

        # 全部 step 完成→提示 agent 调 plan_mode_off 收尾
        if self.session and self.session.plan:
            final_msg = "系统提示：所有 Plan Step 已执行完毕，请调用 plan_mode_off 结束 plan 模式。"
            return self.loop.run_turn(agent=agent,message=final_msg)
        return last_result

    # 拼接单个 step 的执行提示（描述/验收标准/产出物/执行约束）
    def _build_step_prompt(self,step)->str:
        return (
            f"系统提示：当前需要执行Plan Step {step.step_number}\n\n"
            f"{step.description}\n\n"
            f"验收标准：{step.acceptance_criteria}\n\n"
            f"产出物请放置于：{self.session.plan.output_file}\n\n"
            f"当前处于 plan 执行阶段。请执行此 step，完成后使用 plan_update 工具更新状态为 done 并记录结果。\n\n"
            f"注意：\n"
            f"1. 请勿自行调用 plan_mode_off，等待所有 step 执行完毕后系统会自动提示使用此工具。\n"
            f"2. 本轮循环使用 plan_update 需严格仅更新本轮系统提示对应的 step，不可连续调用更新其他 step。\n\n"
            f"提示：如果本 step 可拆解为多个互相独立、不依赖彼此结果的子任务，可考虑使用 subagent_create 并行处理；否则直接执行，无需强行拆分。"
        )
