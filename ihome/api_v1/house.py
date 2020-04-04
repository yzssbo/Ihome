import datetime
import json

from ihome.utils.commons import login_required
from ihome.utils.image_storage import storage
from . import api
from flask import session, jsonify, current_app, request, g

from ihome import redis_cli, constants, db
from ihome.models import Area, House, Facility, HouseImage, User, Order
from ihome.utils.response_code import RET


@api.route('/session', methods=['GET'])
def check_session():
    """
    检查用户登录信息获取展示
    :return:
    """
    name = session.get('name')
    if name is not None:
        return jsonify(errno=RET.OK, errmsg='OK', data={'name': name})
    else:
        return jsonify(errno=RET.SESSIONERR, errmsg='FALSE')


@api.route('/areas', methods=['GET'])
def get_area_info():
    """
    城区信息加载: 缓存 ----- 磁盘 ----- 缓存
    1. 读取redis数据城区信息
    2. 判断获取结果,  如果有数据,直接返回城区信息
    3. 城区信息动态加载, 不同时间访问数据可能存在差异, 需要记录访问历史
    4. 没有获取到 去mysql查询
    5. 遍历查询结果, 因为flask_sqlalchemy返回的是查询对象, 调用模型类to_dict方法转成字典数据返回
    6. 把城区数据转成json,存入redis
    7. 返回城区信息
    :return: 
    """
    try:
        areas = redis_cli.get('area_info')
    except Exception as e:
        current_app.logger.error(e)
        areas = None
    # 判断查询结果
    if areas:
        # 因为城区信息时动态加载的, 记录访问记录
        current_app.logger.info('hit redis areas info')
        # 从redis中取出的数据就是json格式  不适用jsonify
        return '{"errno":"0", "errmsg": "OK", "data": %s}' % areas
    # 查询mysql
    try:
        areas = Area.query.all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询城区数据失败')
    # 判断查询结果
    if areas is None:
        return jsonify(errno=RET.NODATA, errmsg='无城区信息')
    # 遍历城区列表信息, 把查询对象转换成字典数据
    areas_list = []
    for area in areas:
        areas_list.append(area.to_dict())
    # 把城区信息转成json, 存入redis
    areas_json = json.dumps(areas_list)
    try:
        redis_cli.setex('area_info', constants.AREA_INFO_REDIS_EXPIRES, areas_json)
    except Exception as e:
        current_app.logger.error(e)
    # 拼接json数据进行返回
    resp = '{"errno":"0", "errmsg": "OK", "data": %s}' % areas_json
    return resp


@api.route('/houses', methods=['POST'])
@login_required
def save_house_info():
    """
    发布新房源
    1. 获取参数, g.user_id, 房屋的基本信息, 配套设施
    2. 判断json数据包是否存在
    3. 获取详细参数信息
    4. 判断房屋基本信息的完整性
    5. 价格参数: 前端价格以元为单位, 后端数据以分为单位保存
    6. 构造模型类对象, 保存房屋数据
    7. 判断配套设施参数, 如有保存, 否则不存
    8. 提交数据, 返回结果{房屋id}

    :return:
    """
    # 获取json数据包
    json_data = request.get_json()
    if not json_data:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 提取房屋参数信息
    title = json_data.get('title')
    area_id = json_data.get('area_id')
    price = json_data.get('price')
    address = json_data.get('address')
    room_count = json_data.get('room_count')
    acreage = json_data.get('acreage')
    unit = json_data.get('unit')
    capacity = json_data.get('capacity')
    beds = json_data.get('beds')
    deposit = json_data.get('deposit')
    min_days = json_data.get('min_days')
    max_days = json_data.get('max_days')
    if not all([title, price, address, area_id, room_count, acreage, unit, capacity, beds, deposit, min_days, max_days]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数缺失')
    # 对价格参数单位进行转换
    try:
        price = int(float(price) * 100)
        deposit = int(float(deposit) * 100)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR, errmsg='金额格式错误')
    # 保存房屋信息
    house = House()
    house.user_id = g.user_id
    house.area_id = area_id
    house.title = title
    house.price = price
    house.address = address
    house.room_count = room_count
    house.acreage = acreage
    house.unit = unit
    house.capacity = capacity
    house.beds = beds
    house.deposit = deposit
    house.min_days = min_days
    house.max_days = max_days
    # 尝试获取房屋配套设施参数
    facility = json_data.get('facility')
    if facility:
        # 对胚胎设施进行校验, 该设施在数据库有存储
        try:
            facilities = Facility.query.filter(Facility.id.in_(facility)).all()
            house.facilities = facilities
        except Exception as e:
            current_app.logger.error(e)

    try:
        db.session.add(house)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg='数据保存异常')
    else:
        return jsonify(errno=RET.OK, errmsg='OK', data={'house_id': house.id})




@api.route('/houses/<int:house_id>/images', methods=['POST'])
@login_required
def save_house_image(house_id):
    """
    保存房屋图片
    1. 获取图片参数  house_image
    2. 根据房屋id参数 确认房屋的存在
    3. 读取图片数据, 调用七牛云, 上传图片
    4. 保存房屋图片数据, 房屋图片表和房屋表默认图片
    5. 拼接房屋图片的绝对地址
    6. 返回图片的URL
    :param house_id:
    :return:
    """
    image = request.files.get('house_image')
    if not image:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 根据路径参数房屋id查询房屋
    try:
        house = House.query.get(house_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询数据失败')
    if not house:
        return jsonify(errno=RET.NODATA, errmsg='没有找到房屋')
    # 读取图片数据
    image_byte = image.read()
    try:
        image_name = storage(image_byte)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR, errmsg='第三方异常')
    # 保存房屋图片数据, 房屋表, 房屋图片表
    house_img = HouseImage()
    house_img.house_id = house_id
    house_img.url = image_name
    # 如果房屋未设置主图片
    if not house.index_image_url:
        house.index_image_url = image_name
    try:
        db.session.add_all([house_img, house])
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg='数据保存失败')
    # 拼接图片的绝对路径返回渲染
    image_url = constants.QINIU_DOMIN_PREFIX + image_name
    return jsonify(errno=RET.OK, errmsg='OK', data={'url': image_url})


@api.route('/user/houses', methods=['GET'])
@login_required
def get_user_houses():
    """
    获取用户发布的房屋信息
    :return:
    """
    # 获取用户身份id
    user_id = g.user_id
    try:
        user = User.query.get(user_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询失败')

    if user:
        houses = user.houses
        houses_list = []
        if houses:
            for house in houses:
                houses_list.append(house.to_basic_dict())
            return jsonify(errno=RET.OK, errmsg='OK', data={'houses': houses_list})
        else:
            return jsonify(errno=RET.NODATA, errmsg='没有找到对应房屋信息')
    else:
        return jsonify(errno=RET.NODATA, errmsg='没有对应用户')



@api.route('/houses/index', methods=['GET'])
def get_houses_index():
    """
    获取首页房屋幻灯片信息：缓存---磁盘---缓存
    1.尝试从redis中获取房屋信息
    2.如果有数据，留下访问记录，拼接字符串返回json数据
    3.查询mysql，房屋：成交量较高的
    4.遍历查询结果，判断房屋是否有主图片，默认操作：无图不添加数据
    5.把列表存入redis中
    6.返回房屋信息
    :return:
    """
    house_index_info = None
    try:
        house_index_info = redis_cli.get('house_index_info')
    except Exception as e:
        current_app.logger.error(e)

    if house_index_info:
        current_app.logger.info('hit redis house index info')
        return '{"errno": "0", "errmsg": "OK", "data":%s}' % house_index_info

    try:
        houses = House.query.order_by(House.order_count.desc()).limit(constants.HOME_PAGE_MAX_HOUSES)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询失败')
    if not houses:
        return jsonify(errno=RET.NODATA, errmsg='无房屋数据')
    # 定义容器, 存储查询结果
    houses_list = []
    for house in houses:
        if not house.index_image_url:
            continue
        houses_list.append(house.to_basic_dict())
    # 转json存入redis
    houses_json = json.dumps(houses_list)
    try:
        redis_cli.setex('house_index_info', constants.HOME_PAGE_DATA_REDIS_EXPIRES, houses_json)
    except Exception as e:
        current_app.logger.error(e)
    return '{"errno":"0", "errmsg":"OK", "data":%s}' % houses_json



@api.route('/houses/<int:house_id>', methods=['GET'])
def get_houses_detail(house_id):
    """
    首页幻灯片查看房间详情
    :param house_id:
    :return:
    """
    user_id = session.get("user_id", -1)

    # 先从 redis 中查询
    try:
        house_dict = redis_cli.get("house_info_%d" % house_id)
        if house_dict:
            return '{"errno":"0", "errmsg": "OK", "data":{"house":%s,"user_id":%s}}' % (house_dict, user_id)
    except Exception as e:
        current_app.logger.error(e)

    # 如果redis中没有查询到
    try:
        house = House.query.get(house_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="房屋信息查询失败")
    if not house:
        return jsonify(errno=RET.NODATA, errmsg="房屋信息不存在")

    # 将数据缓存到redis中

    house_dict = house.to_full_dict()

    json_dict = json.dumps(house_dict)

    try:
        redis_cli.setex(("house_info_%d" % house_id), constants.HOUSE_DETAIL_REDIS_EXPIRE_SECOND, json_dict)
    except Exception as e:
        current_app.logger.error(e)

    return '{"errno":"0", "errmsg": "OK", "data":{"house":%s,"user_id":%s}}' % (house_dict, user_id)



# 搜索房屋/获取房屋列表
@api.route('/houses')
def get_house_list():
    # 获取所有的参数
    args = request.args
    area_id = args.get('aid', '')
    start_date_str = args.get('sd', '')
    end_date_str = args.get('ed', '')
    # booking(订单量), price-inc(低到高), price-des(高到低),
    sort_key = args.get('sk', 'new')
    page = args.get('p', '1')

    try:
        page = int(page)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")

    # 日期转换
    try:
        start_date = None
        end_date = None
        if start_date_str:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
        if end_date_str:
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
        # 如果开始时间大于或者等于结束时间，就报错
        if start_date and end_date:
            assert start_date < end_date, Exception("开始时间大于结束时间")
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")

    # 从缓存中取出房屋列表
    try:
        redis_key = "houses_%s_%s_%s_%s" % (start_date_str, end_date_str, area_id, sort_key)
        res_json = redis_cli.hget(redis_key, page)
        if res_json:
            current_app.logger.info('hit redis %s' % redis_key)
            return res_json
    except Exception as e:
        current_app.logger.error(e)

    filters = []
    # 判断是否传入城区id
    if area_id:
        # 此处列表里面添加的是sqlalchemy对象, sqlalchemy底层重写了list的 __eq__方法, 一般添加的是布尔值
        filters.append(House.area_id == area_id)

    # 过滤已预订的房屋
    conflict_order = None
    try:
        if start_date and end_date:
            conflict_order = Order.query.filter(Order.begin_date <= end_date, Order.end_date >= start_date).all()
        elif start_date:
            conflict_order = Order.query.filter(Order.end_date >= start_date).all()
        elif end_date:
            conflict_order = Order.query.filter(Order.begin_date <= end_date).all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="查询数据错误")

    if conflict_order:
        # 取到冲突订单的房屋id
        conflict_house_id_list = [order.house_id for order in conflict_order]
        # 添加条件：查询出房屋不包括冲突订单中的房屋id
        filters.append(House.id.notin_(conflict_house_id_list))
    print(filters)

    # 根据筛选条件进行排序
    if sort_key == "booking":
        # 解包filters列表
        house_query = House.query.filter(*filters).order_by(House.order_count.desc())
    elif sort_key == "price-inc":
        house_query = House.query.filter(*filters).order_by(House.price.asc())
    elif sort_key == "price-des":
        house_query = House.query.filter(*filters).order_by(House.price.desc())
    else:
        house_query = House.query.filter(*filters).order_by(House.create_time.desc())

    # 进行分页
    paginate = house_query.paginate(page, constants.HOUSE_LIST_PAGE_CAPACITY, False)
    # 取到当前页数据
    houses = paginate.items
    # 取到总页数
    total_page = paginate.pages
    # 获取当前页码
    current_page = paginate.page
    print(current_page)
    # 将查询结果转成字符串
    houses_list = []
    for house in houses:
        houses_list.append(house.to_basic_dict())

    resp = {"errno": "0", "errmsg": "OK", "data": {"total_page": total_page, "houses": houses_list}}
    resp_json = json.dumps(resp)
    # response_data = {"total_page": total_page, "houses": houses_dict}
    try:
        redis_key = "houses_%s_%s_%s_%s" % (start_date_str, end_date_str, area_id, sort_key)
        # 创建redis管道, 支持多命令事务
        pipe = redis_cli.pipeline()
        # 开启事务
        pipe.multi()
        # 设置数据
        pipe.hset(redis_key, page, resp_json)
        # 设置过期时间
        pipe.expire(redis_key, constants.HOUSE_LIST_REDIS_EXPIRES)
        # 提交事务
        pipe.execute()
    except Exception as e:
        current_app.logger.error(e)


    return resp_json