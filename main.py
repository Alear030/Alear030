from core import loop
from session import session_init,judge_compress


session_id = session_init()
session_round = 0

while True:
    loop(session_id= session_id,session_round = session_round)
    session_round+=1
    judge_compress(session_id=session_id)