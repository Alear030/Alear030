## plan_mode_off 工具

用途: 结束 plan 执行模式。所有 plan step 已执行完毕后调用，将 plan 状态从 in_progress 切换为 done，session 恢复普通模式。

调用规则: 所有 plan step 全部执行完毕且已通过 plan_update 更新后，调用此工具结束 plan 模式。

何时使用:
- 所有 plan step 已执行完成，且已通过 plan_update 更新状态
- 收到系统提示要求调用 plan_mode_off

何时不要使用:
- plan 尚未执行完毕
- 有 step 尚未通过 plan_update 更新
- 不是 plan 执行模式

参数:
- plan_file (必填): plan 文件名（不含路径和 .json 后缀）

调用后的行为:
- plan 状态从 in_progress 切换为 done
- session 恢复普通模式
