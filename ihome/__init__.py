from flask import Flask
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from config import config_dict, DefaultConfig

import logging
from logging.handlers import RotatingFileHandler
from redis import StrictRedis
from flask_wtf import CSRFProtect

redis_cli = StrictRedis(host=DefaultConfig.REDIS_HOST, port=DefaultConfig.REDIS_PORT, db=2, decode_responses=True)
db = SQLAlchemy()
csrf = CSRFProtect()


# 集成项目日志
# 设置日志的记录等级
logging.basicConfig(level=logging.DEBUG)  # 调试debug级
# 创建日志记录器，指明日志保存的路径、每个日志文件的最大大小、保存的日志文件个数上限
file_log_handler = RotatingFileHandler("/Users/yjp/Desktop/Flask-ihome/logs/log", maxBytes=1024*1024*100, backupCount=10)
# 创建日志记录的格式                 日志等级    输入日志信息的文件名 行数    日志信息
formatter = logging.Formatter('%(levelname)s %(filename)s:%(lineno)d %(message)s')
# 为刚创建的日志记录器设置日志记录格式
file_log_handler.setFormatter(formatter)
# 为全局的日志工具对象（应用程序实例app使用的）添加日后记录器
logging.getLogger().addHandler(file_log_handler)




# 定义成工厂函数, 代码封装,可以根据函数的参数动态的指定程序实例,使用不同环境下的配置
def create_app(conf_name):
    app = Flask(__name__)
    app.config.from_object(config_dict[conf_name])

    Session(app)
    db.init_app(app)
    csrf.init_app(app)


    # 导入蓝图对象, 注册蓝图对象给程序实例app
    from ihome.api_v1 import api
    app.register_blueprint(api)

    # 导入自定义的转换器
    from ihome.utils.commons import RegexConverter
    app.url_map.converters['regex'] = RegexConverter

    # 导入静态资源访问的蓝图
    from ihome.web_page import html
    app.register_blueprint(html)

    return app

