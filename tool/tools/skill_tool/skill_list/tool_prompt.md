## skill_list 工具

用途: 扫描 `skill/` 下各 `skill.md` 的 YAML frontmatter，返回 `skill_name` + `skill_description` 列表。

何时使用:
- 需要主动枚举磁盘上全部技能时

何时不要使用:
- 日常命中某技能后应直接 `skill_load`，不必先 list
- 启动时可用技能已在 system prompt 列表里，不必再扫一遍

参数:
- 无模型可见参数

注意事项:
- 只读 frontmatter 的 name/description，不返回技能正文
