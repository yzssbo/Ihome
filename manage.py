from flask import session
from flask_script import Manager
from flask_migrate import Migrate, MigrateCommand
from ihome import create_app, db, models


app = create_app('def')
# 实例化manager管理对象
manager = Manager(app)
# 使用迁移框架
Migrate(app, db)
# 添加迁移命令, db就是字符串可以随意指定, MigrateCommand里面有迁移指令
manager.add_command('db', MigrateCommand)





if __name__ == '__main__':

    manager.run()
