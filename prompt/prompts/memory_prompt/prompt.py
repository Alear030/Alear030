import json

from prompt.prompt_register import register_prompt


from config import MEMORY_STORAGE_PATH

@register_prompt(prompt_name='memory_prompt',order=35,condition=lambda agent:agent.agent_name == 'main')
def memory_prompt(agent)->str:
    
    # 得到user.json的信息
    user_path = MEMORY_STORAGE_PATH/'user.json'
    if user_path.exists():
        user_json = user_path.read_text(encoding='utf-8').strip()
    else:
        return
    # 解析userjson
    if user_json:
        user_content = json.loads(user_json)
    else:
        return

    # 空画像不注入(避免空标题污染 system prompt)
    # 顶层必须是 list；曾被写成 ["系统错误"] 这类 list[str] 时直接跳过，避免 dim.get 崩启动
    if not isinstance(user_content, list) or not user_content:
        return
    
    # 对user信息进行拼接
    user_info = '# Alear030大人的个人信息\n\n'
    has_valid = False
    for dim in user_content:
        # 跳过非 dict / 缺 type_name 的维度(结构异常防御)
        if not isinstance(dim, dict) or not dim.get('type_name'):
            continue
        # 过滤出有 info 内容的条目;无有效条目的维度不输出(避免空维度标题,如 #4 过滤无 info_source 后变空)
        info_list = dim.get('info_list', [])
        if not isinstance(info_list, list):
            continue
        valid_pieces = [
            piece for piece in info_list
            if isinstance(piece, dict) and piece.get('info')
        ]
        if not valid_pieces:
            continue
        has_valid = True
        user_info += f"## Alear030大人's{dim['type_name']}\n\n"
        for piece in valid_pieces:
            user_info += f" - {piece['info']}\n\n"

    return user_info if has_valid else None
# done(@claude): 检查并优化--空画像/空维度不注入空标题;结构异常(type_name/info缺)防御性跳过;slice变量名改dim避免遮蔽内置
    

