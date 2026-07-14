import json

from pathlib import Path

from tool.tool_core import register_tool


tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip() if tool_prompt_file.exists() else None


# 统一组装工具层的结构化 JSON 返回协议。
def _result(status, question, answer_type=None, selected_index=None, selected_option=None, answer=None, error=None):
    return json.dumps({
        'status': status,
        'question': question,
        'answer_type': answer_type,
        'selected_index': selected_index,
        'selected_option': selected_option,
        'answer': answer,
        'error': error
    }, ensure_ascii=False)


# 反复读取非空输入；中断时返回 None 交由调用方决定取消语义。
def _read_nonempty(prompt):
    while True:
        try:
            answer = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            # 输入中断统一交给上层转为结构化 cancelled，避免把 REPL 一并终止。
            return None
        if answer:
            return answer
        print('输入不能为空，请重新输入。')


@register_tool(
    tool_name='ask_user_question',
    tool_desc='当任务缺少会实质改变后续路径的用户目标、偏好或取舍时，向用户发起一个问题并等待结构化回答。',
    tool_prompt=tool_prompt,
    tool_enabled=True,
    tool_autho='interaction_tool'
)
# 向用户收集开放回答或有限选项，并按统一 JSON 协议返回结果。
def ask_user_question(question: str, options: list[dict] = None, **kwargs) -> str:
    # 先拒绝无效问题，避免进入任何交互后才发现没有可展示的内容。
    if not isinstance(question, str) or not question.strip():
        return _result(
            'error',
            question if isinstance(question, str) else None,
            error={'code': 'invalid_question', 'message': 'question 必须是非空字符串。'}
        )

    question = question.strip()
    # 未提供选项时保留自由输入路径，调用方不必为了开放问题伪造菜单。
    if options is None:
        print(f'\n[需要你的决定]\n{question}')
        answer = _read_nonempty('请输入你的想法: ')
        if answer is None:
            return _result(
                'cancelled',
                question,
                error={'code': 'input_interrupted', 'message': '用户输入被中断。'}
            )
        return _result('answered', question, 'custom', answer=answer)

    # 选项数量受限于交互菜单；范围外直接返回协议错误，不进入后续编号处理。
    if not isinstance(options, list) or not 2 <= len(options) <= 4:
        return _result(
            'error',
            question,
            error={'code': 'invalid_options', 'message': 'options 必须是包含 2-4 项的列表，或省略以使用自由输入。'}
        )

    # 展示前将选项校验、去空白并复制为稳定的菜单/回传数据。
    normalized_options = []
    for option in options:
        if not isinstance(option, dict) or not isinstance(option.get('label'), str) or not option['label'].strip():
            return _result(
                'error',
                question,
                error={'code': 'invalid_options', 'message': '每个选项都必须包含非空字符串 label。'}
            )
        if 'description' in option and not isinstance(option['description'], str):
            return _result(
                'error',
                question,
                error={'code': 'invalid_options', 'message': '选项 description 缺省或为字符串。'}
            )
        normalized_options.append({
            'label': option['label'].strip(),
            'description': option.get('description', '').strip()
        })

    # 准备并展示编号菜单；末位固定留给自由输入，编号同时作为 selected_index 返回。
    custom_index = len(normalized_options) + 1
    print(f'\n[需要你的决定]\n{question}')
    for index, option in enumerate(normalized_options, start=1):
        print(f'{index}. {option["label"]}')
        if option['description']:
            print(f'   {option["description"]}')
    print(f'{custom_index}. 其他，请自行输入')

    # 循环读取菜单编号；非法输入留在当前步骤重试，中断则返回 cancelled。
    while True:
        try:
            selected = input('请选择编号: ').strip()
        except (EOFError, KeyboardInterrupt):
            return _result(
                'cancelled',
                question,
                error={'code': 'input_interrupted', 'message': '用户输入被中断。'}
            )
        if not selected.isdigit() or not 1 <= int(selected) <= custom_index:
            print(f'请输入 {1}-{custom_index} 之间的编号。')
            continue

        selected_index = int(selected)
        # 末位是自由输入分支，返回 custom 类型结果。
        if selected_index == custom_index:
            answer = _read_nonempty('请输入你的想法: ')
            if answer is None:
                return _result(
                    'cancelled',
                    question,
                    error={'code': 'input_interrupted', 'message': '用户输入被中断。'}
                )
            return _result('answered', question, 'custom', answer=answer)

        # 其余编号映射到预设选项，返回 option 类型结果。
        selected_option = normalized_options[selected_index - 1]
        return _result(
            'answered',
            question,
            'option',
            selected_index=selected_index,
            selected_option=selected_option,
            answer=selected_option['label']
        )
