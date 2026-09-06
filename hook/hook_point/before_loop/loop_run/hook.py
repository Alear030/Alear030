from hook.hook_core import hooks
from eval import Trace

@hooks.register(
    hook_point="before_loop",
    background=False,
    priority=1,
    order=1,
    enabled=True
)
def user_input_assembled_procced(session=None,**kwargs):
    content = kwargs.get("content",None)
    if session is None or content is None:
        return

    content["attachment_content"]["content"] = session.attachment.attachment_render(attachment_target = content["agent_name"])

    if content["attachment_content"]["content"]:
        Trace.trace_record(
            trace_type="input",
            source="attachment",
            loop_round=session.round,
            trace_detail={"input_message":content["attachment_content"]["content"]}
        )