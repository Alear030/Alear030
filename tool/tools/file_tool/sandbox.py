from config import WORK_SPACE,ROOT_DIRECTORY,FILE_EDIT_SANDBOX

SKILL_DIRECTORY = ROOT_DIRECTORY/'skill'


# file_write/file_edit 共用的写入路径闸门:放行返回 None,拒绝返回错误文案;对模型的说明走 file_sandbox_prompt 的 attachment
# 两边都 resolve 再比:workspace 经符号链接/联接或 subst 盘符访问时,只解析一边会把合法写入全部拒掉
def check_write_path(resolved_path,action:str):
    if not FILE_EDIT_SANDBOX:
        return None
    if resolved_path.is_relative_to(WORK_SPACE.resolve()) or resolved_path.is_relative_to(SKILL_DIRECTORY.resolve()):
        return None
    return f'错误，当前{action}路径非工作空间，沙箱模式下只能在工作空间或技能目录{action}文件，工作空间地址：{WORK_SPACE}，技能目录：{SKILL_DIRECTORY}'
