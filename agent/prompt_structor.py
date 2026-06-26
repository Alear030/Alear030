from config import ROOT_DIRECTORY

from core import rich_print

def _get_agent_prompt(type:str,role:str)->str:
    agent_memory = ROOT_DIRECTORY/f'agent/agent_prompt/{role}_agent.md'
    if not agent_memory.exists():
        rich_print(message=f'{role} agent_memory dose not exist...',type='system_error')
        return ''
    else:
        rich_print(message=f'{role} agent_memory has been loaded...',type='system_message')
        agent_memory_content = agent_memory.read_text(encoding='utf-8')
        return agent_memory_content.strip() if agent_memory_content.strip() else ''
    
    
def _get_system_prompt(type:str,role:str)->str:
    system_prompt_file = ROOT_DIRECTORY/'agent/system_prompt.md'
    system_prompt_content = system_prompt_file.read_text(encoding='utf-8') if system_prompt_file.exists() else None
    
    if not system_prompt_content:
        rich_print(message=f'{role} system_prompt does not exist...',type='system_error')
        return ''
    
    system_prompt_content_detail = system_prompt_content.strip() if system_prompt_content.strip() else None
    if system_prompt_content_detail:
        rich_print(message=f'{role} system_prompt has been loaded...',type='system_message')
        return system_prompt_content_detail


def prompt_structor(type:str,role:str)->str:
    system_prompt = _get_system_prompt(type=type,role=role) if role == 'main' else ''
    agent_prompt = _get_agent_prompt(type=type,role=role)
    return system_prompt + '\n\n' + agent_prompt