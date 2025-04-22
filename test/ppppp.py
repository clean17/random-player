n = int(input('입력값'))
arr = ['*']
for i in range(0, n, 2):
    s = ' '*(int((n-i)/2))+'*'*(i+1)
    print(s)