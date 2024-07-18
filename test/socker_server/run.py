import os
import http.server
import socketserver

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='G:/', **kwargs)

    def do_GET(self):
        # 파일 경로를 직접 지정, 파일이 있는지 확인
        requested_path = self.translate_path(self.path)
        if os.path.isfile(requested_path):
            super().do_GET()
        else:
            self.send_error(404, "File not found")

PORT = 8000

with socketserver.TCPServer(("", PORT), MyHandler) as httpd:
    print(f"Serving at port {PORT}")
    httpd.serve_forever()
