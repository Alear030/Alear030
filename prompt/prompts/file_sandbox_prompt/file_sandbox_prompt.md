## 文件写入沙箱

当前开启了文件写入沙箱，file_write 与 file_edit 只能作用于工作空间或技能目录内的文件。

**工作空间**：当前 checkout 根目录下的 `workspace/`（与 file_glob、file_grep 不传 path 时的默认目录相同；file_write/file_edit 校验以此为准）

**技能目录**：当前 checkout 根目录下的 `skill/`（创建/修改技能文件 skill/<name>/skill.md 时使用）

**查看工作空间内容时，优先用 file_glob（不传 path）或 file_grep，不要自行假设绝对路径**

**如果写入或编辑的目标路径不在工作空间或技能目录下，请严格拒绝**
