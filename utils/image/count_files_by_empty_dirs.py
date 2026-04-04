import os
import shutil

def count_files_by_empty_dirs(a_dir, b_dir, c_dir):
    empty_dirs = []

    # 1. a_dir의 자식 디렉토리 중, 내부에 파일이 하나도 없는 디렉토리 찾기
    for name in os.listdir(a_dir):
        path = os.path.join(a_dir, name)
        if os.path.isdir(path):
            has_file = False
            for root, dirs, files in os.walk(path):
                if files:
                    has_file = True
                    break

            if not has_file:
                empty_dirs.append(name)

    # 2. b_dir의 "파일만" 가져오기
    b_files = [
        f for f in os.listdir(b_dir)
        if os.path.isfile(os.path.join(b_dir, f))
    ]

    c_files = [
        f for f in os.listdir(c_dir)
        if os.path.isfile(os.path.join(c_dir, f))
    ]

    # 중복 제거
    all_files = list(set(b_files + c_files))

    # 3. 각 디렉토리 이름으로 시작하는 b_dir 파일 개수 세기
    result = {}
    for d in empty_dirs:
        count = sum(1 for f in all_files if f.startswith(d))
        result[d] = count

    # 4. x개인 디렉토리는 a_dir에서 삭제
    deleted_dirs = []
    for d, count in result.items():
        if count <= 1:
            dir_path = os.path.join(a_dir, d)
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                shutil.rmtree(dir_path)
                print(f"https://www.instagram.com/{d}: {count}")
                deleted_dirs.append(d)

    # 5. 삭제 후 남은 결과만 내림차순 정렬
    filtered_result = {k: v for k, v in result.items() if v > 0}
    sorted_result = sorted(filtered_result.items(), key=lambda x: x[1], reverse=True)

    # 6. 출력
    for d, count in sorted_result:
        if count < 5:
            print(f"https://www.instagram.com/{d}: {count}")
        else:
            print(f"{d}: {count}")

    if deleted_dirs:
        print("\n삭제된 디렉토리:")
        for d in deleted_dirs:
            print(d)

    return dict(sorted_result), deleted_dirs


a = r''
b =  r''
c =  r''
count_files_by_empty_dirs(a, b, c)