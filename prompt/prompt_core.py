from .prompt_register import build_prompt

class Prompt:

    def __init__(self,agent):
        self.prompt_content:str = build_prompt(agent)