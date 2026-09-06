import yaml

from pathlib import Path

from prompt import prompt
from config import ROOT_DIRECTORY
from log.log_core import Log

PROMPT_DIR = Path(__file__).parent


# 技能使用原则 + 全部已注册技能的名称和描述
# create-skill 技能会在运行时往 skill/ 写新技能,内容 session 内就可能变,故走 attachment
# target 手工对齐 agents.yaml 里 skill_tool: true 的 agent,改授权时这里要跟着改
@prompt.register_prompt(prompt_name='skill_prompt',order=20,type="notification",target=['main','plan'])
def build()->str:
    skill_prompt = ''
    skill_prompt_file = PROMPT_DIR/'skill_prompt.md'
    if skill_prompt_file.exists():
        text = skill_prompt_file.read_text(encoding='utf-8')
        skill_prompt = text + '\n\n' if text else ''

    skill_path = ROOT_DIRECTORY/'skill'
    # 枚举也在网内:目录遍历期的 OSError 若逃出去就是外网整块兜,全部技能陪葬
    # sorted 定死顺序:文件系统枚举序不保证稳定,技能列表每次换个排法只是无谓噪音
    try:
        skill_list = sorted(skill_path.rglob('skill.md'))
    except Exception as e:
        Log.pending_record(level='high',source='skill_prompt',event='skill_enumerate_fail',detail={
            'skill_file':str(skill_path),'error':f'{type(e).__name__}: {e}'})
        skill_list = []
    for skill_file in skill_list:
        # 内网兜单个技能文件:语法/编码/形状损坏只丢这一个并带路径记账,其余技能照常注入
        # build_prompt 的外网粒度是分块,一个坏文件会把全部技能陪葬,数据失败必须就近兜
        try:
            skill_content = skill_file.read_text(encoding='utf-8')
            if not skill_content.startswith('---'):
                continue
            skill_file_parts = skill_content.split('---')
            skill_yaml = skill_file_parts[1].strip()
            skill_metadata = yaml.safe_load(skill_yaml)
            if not isinstance(skill_metadata, dict):
                Log.pending_record(level='medium',source='skill_prompt',event='skill_load_skip',detail={
                    'skill_file':str(skill_file),'error':'frontmatter 非 dict'})
                continue
            skill_name = skill_metadata.get('name')
            skill_desc = skill_metadata.get('description')
            # 真值校验不够:name: 123/true/[a,b] 都是真值,会把 Python repr 拼进 prompt,必须非空字符串
            if not isinstance(skill_name,str) or not isinstance(skill_desc,str) or not skill_name or not skill_desc:
                Log.pending_record(level='medium',source='skill_prompt',event='skill_load_skip',detail={
                    'skill_file':str(skill_file),'error':'name/description 缺失或非字符串'})
                continue
        except Exception as e:
            Log.pending_record(level='medium',source='skill_prompt',event='skill_load_skip',detail={
                'skill_file':str(skill_file),'error':f'{type(e).__name__}: {e}'})
            continue
        skill_prompt += f'技能名称:{skill_name}  技能描述:{skill_desc}' + '\n\n'
    return skill_prompt
