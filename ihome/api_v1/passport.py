import random
import re

from flask import session, jsonify, current_app, make_response, request

from ihome.utils.response_code import RET
from . import api
from ihome.utils.captcha.captcha import captcha
from ihome import redis_cli, constants, db
from ihome.models import User
from ihome.utils.sms import CCP

@api.route("/imagecode/<image_uuid>", methods=['GET'])
def generate_image_code(image_uuid):
    """
    生成图片验证码
    1.导入captcha工具包
    2.生成图片验证码，获取文本和图片
    3.存入redis数据库中，存文本
    4.返回前端图片，把响应类型改成image/jpg
    :param image_code_id:
    :return:
    """
    text, image = captcha.generate_captcha()
    # 在redis中保存图片验证码文本
    try:
        redis_cli.setex('ImageCode_' + image_uuid, constants.IMAGE_CODE_REDIS_EXPIRES, text)
    except Exception as e:
        # 使用应用上下文对象，记录项目日志
        current_app.logger.error(e)
        # 返回错误信息,前后端数据交互格式应该使用json
        return jsonify(errno=RET.DBERR, errmsg='数据保存失败')
    resp = make_response(image)
    resp.headers['Content-Type'] = 'image/jpg'

    return resp


@api.route("/smscode/<mobile>", methods=['GET'])
def send_sms_code(mobile):
    """
    发送短信接口
    1. 获取参数, 查询字符串方式, 输入的图片验证码和uuid
    2. 检查参数的完整性
    3. 正则校验手机号码格式
    4. 从redis中取出真实的图片验证码
    5. 判断redis中的获取结果
    6. 先把redis中的图片验证码内容删除
    7. 比较图片验证码是否正确
    8. 生成短信的随机码, 存入redis
    9. 调用云通信发送短信
    10. 获取发送结果
    :param mobile:
    :return:
    """
    # 获取查询字符串参数
    image_code = request.args.get('text')
    uuid = request.args.get('id')
    # 检查参数完整性
    if not all([mobile, image_code, uuid]):
        return jsonify(errno=RET.PARAMERR, errmsg='缺少必传参数')
    # 校验手机格式
    if not re.match(r'1[3-9]\d{9}$', mobile):
        return jsonify(errno=RET.PARAMERR, errmsg='手机格式错误')
    # 从redis中取出真实的图片验证码文本内容
    try:
        server_image_code = redis_cli.get('ImageCode_' + uuid)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询数据失败')
    # 判断获取结果
    if not server_image_code:
        return jsonify(errno=RET.DATAERR, errmsg='无效的id')
    # 删除图片验证码
    try:
        redis_cli.delete('ImageCode_' + uuid)
    except Exception as e:
        current_app.logger.error(e)
    # 比较图片验证码
    if image_code.lower() != server_image_code.lower():
        return jsonify(errno=RET.DATAERR, errmsg='验证码错误')
    # 检验手机号是否注册
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='数据库异常')
    if user:
        return jsonify(errno=RET.DATAEXIST, errmsg='手机号已注册')
    # 生成6位短信验证码
    sms_code = '%06d' % random.randint(1, 999999)
    current_app.logger.info(sms_code)
    # 存入redis
    try:
        pl = redis_cli.pipeline()
        pl.setex('SMSCode_' + mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        pl.execute()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='保存数据失败')
    # 调用云通讯发送短信
    try:
        sms = CCP()
        sms.send_template_sms(mobile, [sms_code, 5], 1)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR, errmsg='发送短信异常')

    return jsonify(errno=RET.OK, errmsg='发送成功')


@api.route("/users", methods=['POST'])
def register():
    """

    :return:
    """
    # request.json.get()  获取单个json数据
    # 获取整个json数据包
    json_data = request.get_json()
    if not json_data:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 从json数据包中挨个提取参数
    mobile = json_data.get('mobile')
    sms_code = json_data.get('sms_code')
    password = json_data.get('password')
    if not all([mobile, sms_code, password]):
        return jsonify(errno=RET.PARAMERR, errmsg='缺少必传参数')
    # 校验手机号
    if not re.match(r'1[3-9]\d{9}$', mobile):
        return jsonify(errno=RET.PARAMERR, errmsg='手机格式错误')
    # 从redis中取出真实的短信验证码
    try:
        server_sms_code = redis_cli.get('SMSCode_' + mobile)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询数据失败')
    # 判断查询结果
    if not server_sms_code:
        return jsonify(errno=RET.DATAERR, errmsg='数据失效')
    # 先比较  再删除
    if server_sms_code != str(sms_code):
        return jsonify(errno=RET.DATAERR, errmsg='短信验证码错误')
    try:
        redis_cli.delete('SMSCode_' + mobile)
    except Exception as e:
        current_app.logger.error(e)

    # 实例化模型类对象, 保存用户信息
    user = User()
    user.mobile = mobile
    user.name = mobile
    user.password = password
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg='用户注册失败')

    # 缓存用户信息,使用session对象，存到redis中
    session['user_id'] = user.id
    session['name'] = mobile
    session['mobile'] = mobile
    # 返回结果,
    # data表示用户数据，是注册业务完成后，返回注册结果相关的附属信息
    return jsonify(errno=RET.OK, errmsg='注册成功', data=user.to_dict())


@api.route("/sessions", methods=['POST'])
def login():
    """
    用户登录:
    :return:
    """
    # 获取参数, json格式
    json_data = request.get_json()
    if not json_data:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 从json数据包中提取数据
    mobile = json_data.get('mobile')
    password = json_data.get('password')
    if not all([mobile, password]):
        return jsonify(errno=RET.PARAMERR, errmsg='缺少必传参数')
    # 校验手机号
    if not re.match(r'1[3-9]\d{9}$', mobile):
        return jsonify(errno=RET.PARAMERR, errmsg='手机格式错误')
    # 查询数据库
    try:
        user = User.query.filter(User.mobile==mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询失败')
    if not user or not user.check_password(password):
        return jsonify(errno=RET.DATAERR, errmsg='用户名或密码错误')

    # 缓存用户信息在redis中
    session['user_id'] = user.id
    session['mobile'] = mobile
    session['name'] = user.name  # 用户有可能修改用户名, 默认用户名
    # 返回响应
    return jsonify(errno=RET.OK, errmsg='OK', data={'user_id': user.id})









