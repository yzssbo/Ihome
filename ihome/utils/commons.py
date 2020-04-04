import functools

from flask import session, jsonify, g
from werkzeug.routing import BaseConverter
# 定义转换器
# 步骤:
# 1.导入转换器基类
# 2.定义转换器类, 继承基类
# 3.定义函数, 接收参数, 即正则表达式
# 4.添加到默认的转换器字典容器中
from ihome.utils.response_code import RET


class RegexConverter(BaseConverter):
    def __init__(self, url_map, *args):
        super(RegexConverter, self).__init__(url_map)
        self.regex = args[0]


# 实现登录验证装饰器
# 1. 使用session对象, 从redis中取出缓存的用户信息
# 2. 判断获取结果, 如果用户登录, 利用g对象保存用户id
def login_required(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        user_id = session.get('user_id')
        if user_id is None:
            return jsonify(errno=RET.SESSIONERR, errmsg='用户未登录')
        else:
            g.user_id = user_id
        return func(*args, **kwargs)
    return wrapper
