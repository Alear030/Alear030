from config import ROOT_DIRECTORY

from core import rich_print

def get_agent(type:str,role:str)->str:
    agent_memory = ROOT_DIRECTORY/f'memory/agent_memory/{role}_agent.md'
    if not agent_memory.exists():
        rich_print(message=f'{role} agent_memory dose not exist...',type='system_error')
        return None
    else:
        rich_print(message=f'{role} agent_memory has been loaded...',type='system_message')
        agent_memory_content = agent_memory.read_text(encoding='utf-8')
        return agent_memory_content.strip() if agent_memory_content.strip() else None
    
    


def get_prompt(type:str,role:str)->str:
    
    system_prompt_file = ROOT_DIRECTORY/'memory/system.md'
    system_prompt_content = system_prompt_file.read_text(encoding='utf-8') if system_prompt_file.exists() else None
    if not system_prompt_content:
        rich_print(message=f'{role} system_prompt does not exist...',type='system_error')
    
    system_prompt_content_detail = system_prompt_content.strip() if system_prompt_content.strip() else None
    if system_prompt_content_detail:
        rich_print(message=f'{role} system_prompt has been loaded...',type='system_message')


    agent_prompt = get_agent(type=type,role=role)

    return system_prompt_content_detail +'\n\n'+ agent_prompt