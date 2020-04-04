# 开发项目  不同额环境 需要使用的配置不同, 利用面向对象思想封装配置项
from redis import StrictRedis


class DefaultConfig(object):
    DEBUG = None
    # 设置redis的ip
    REDIS_HOST = 'localhost'
    # 设置redis的端口
    REDIS_PORT = 6379
    # 设置redis的库
    REDIS_DB = 1
    # 设置秘钥
    SECRET_KEY = 'yzssbo'
    # 配置数据库的链接
    # 安装不上mysqlclient使用pymysql驱动方法
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:yao950724@localhost/ihome?charset=utf8mb4'    # 动态追踪修改, 关闭警告信息
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 配置服务器中session信息存储的位置，redis数据库, session会话默认不过期
    SESSION_TYPE = 'redis'
    SESSION_REDIS = StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    SESSION_USE_SIGNER = True
    PERMANENT_SESSION_LIFETIME = 86400


class DevelopConfig(DefaultConfig):
    DEBUG = True


class ProductionConfig(DefaultConfig):
    DEBUG = False


# 定义不同环境下的配置字典映射
config_dict = {
    'def': DefaultConfig,
    'dev': DevelopConfig,
    'pro': ProductionConfig
}