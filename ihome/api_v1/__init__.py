# 创建蓝图
from flask import Blueprint

api = Blueprint('api', __name__, url_prefix='/api/v1.0')

# 把使用蓝图的文件导入到创建蓝图的下面
from . import passport, users, house, order



# 定义请求钩子, 实现后台返回响应
@api.after_request
def after_request(response):
    if response.headers.get('Content-Type').startswith('text'):
        response.headers['Content-Type'] = 'application/json'
    return response