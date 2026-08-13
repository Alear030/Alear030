## skill_load 工具

用途: 按目录名加载 `skill/<name>/skill.md` 正文（去掉 YAML frontmatter）。

何时使用:
- 任务特征命中某技能 description 之后，动手前必须先 load
- 需要按技能正文执行，而不是凭 description 猜测

何时不要使用:
- 列表里不存在的技能名
- 凭 description 猜内容就开干

参数:
- skill_name (必填): 技能目录名，必须与目录名及 frontmatter `name` 一致

注意事项:
- 找不到对应目录时返回失败串
- 返回的正文才是执行依据，description 只用于命中判断
