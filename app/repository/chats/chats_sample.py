from datetime import datetime

from app.repository.chats.ChatDTO import ChatDTO
from app.repository.chats.chats import insert_chat, find_chats_by_offset, chats_to_line_list, get_chats_count

chat = ChatDTO(created_at=str(datetime.now()), user_id=3, message="칼럼 추가 테스트", chats_room_id=1)
inserted_id = insert_chat(chat)
print("Inserted chat id:", inserted_id)

# # 채팅 범위 조회 예시


# chat_list = get_chats_by_offset(offset=0, limit=10)
# print(chats_to_line_list(chat_list))
# for c in chat_list:
#     print(c)


# all_chat_count = get_chats_count()
# offset = 0
# MAX_FETCH_MESSAGE_SIZE = 50
# sql_offset = min(offset, all_chat_count)
# chat_list = get_chats_by_offset(sql_offset, MAX_FETCH_MESSAGE_SIZE)
# print(chats_to_line_list(chat_list))