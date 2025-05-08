# 깨진 문자 (예: UTF-8을 ISO-8859-1로 잘못 인코딩한 경우)
broken_string = 'ê°ë°ìë²'

# 깨진 문자열을 바이너리 데이터로 변환
bytes_data = broken_string.encode('ISO-8859-1')

# 바이너리 데이터를 올바른 인코딩 방식으로 디코딩
correct_string = bytes_data.decode('UTF-8')

print(correct_string)