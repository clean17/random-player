from users import find_user_by_username, insert_user, update_user_password
from werkzeug.security import generate_password_hash, check_password_hash
from config.config import settings

username = settings['USERNAME']
password = 'e23'

user = find_user_by_username(username)
if user and check_password_hash(user.password, password):
    print("로그인 성공:", user)

# new_user = UserDTO(
#     login_id="testuser",
#     email="test@test.com",
#     password=generate_password_hash("pw1234"),
#     role="USER"
# )
# user_id = insert_user(new_user)

# 수정 예시
# update_user_password('testuser', generate_password_hash("newpw1234"))
