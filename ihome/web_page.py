from flask import Blueprint, make_response, current_app
from flask_wtf import csrf
# s实现静态资源的优化访问
# 原访问路径: http://127.0.0.1:5000/static/html/register.html
# 优化后: http://127.0.0.1:5000/register.html


html = Blueprint('html', __name__)

@html.route('/<regex(".*"):filename>')
def html_file(filename):
    if not filename:
        filename = 'index.html'

    if filename != 'favicon.ico':
        filename = 'html/' + filename

    # 把文件发送给浏览器
    resp = make_response(current_app.send_static_file(filename))

    # 在返回每个视图路由前生成csrf_token写入cookie返回
    csrf_token = csrf.generate_csrf()
    resp.set_cookie('csrf_token', csrf_token)
    return resp

