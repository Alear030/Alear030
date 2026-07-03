## plan_update 工具

用途: 执行plan_mode_on之后，系统注入step执行命令，执行完一轮step对plan进行更新

何时使用:
- 完成 系统注入 某个 step 的全部工作后，更新状态为 done 并记录执行结果
- plan_update工具不可以一轮调用多次，不可以对系统没有注入的step进行update（系统会强制校验 step_number，跳步或提前更新会被拒绝并返回 error）

何时不要使用:
- 对plan未执行plan_mode_on
- 创建或修改 plan 结构（应使用 plan_design）
- step 尚未执行完成
- 系统未注入的step

参数:
- plan_file (必填): plan 文件名（不含路径和 .json 后缀）
- step_number (必填): 要更新的步骤序号，从 1 开始
- status (必填): 步骤状态，如 "done"。后续可扩展其他状态
- result (必填): 步骤执行结果、产出物位置，用一两句话描述执行结果

调用后:
- plan 文件中对应 step 的 status 和 result 被更新
- plan 顶层的 update_time 自动刷新
- 返回更新完成的提示信息
