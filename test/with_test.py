print('test')

class Hello:
    def __enter__(self):
        # 사용할 자원을 가져오거나 만든다(핸들러 등)
        print('enter...')
        return self # 반환값이 있어야 VARIABLE를 블록내에서 사용할 수 있다



    def sayHello(self, name):
        # 자원을 사용한다. ex) 인사한다
        print('hello ' + name)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 마지막 처리를 한다(자원반납 등)
        print('exit...')

with Hello() as h:
    h.sayHello('obama')
    h.sayHello('trump')

#################################################


'''
__enter__       ->  보통 필요한 리소스를 설정하거나 초기화, return 필요
__exit__        ->  컨텍스트 매니저 프로토콜의 일부, with 문 내에서 사용된 리소스를 정리

with 를 지원한다.
'''