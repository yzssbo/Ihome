# -*- coding: utf-8 -*-

import logging


from qiniu import Auth, put_data


# 需要填写你的 Access Key 和 Secret Key
access_key = 'fYdyreH_PqxTs99orVAagwsMEIAo1zx7TQ7qYhGD'
secret_key = '9HTslHU0NY4SSnRP1yFz-kXrSs-v5x33rTiwSGR2'

# 要上传的空间
bucket_name = 'yzs'


def storage(data):
    """七牛云存储上传文件接口"""
    if not data:
        return None
    try:
        # 构建鉴权对象
        q = Auth(access_key, secret_key)

        key = None

        # 生成上传 Token，可以指定过期时间等
        token = q.upload_token(bucket_name, key, 3600)

        # 上传文件
        ret, info = put_data(token, key, data)

    except Exception as e:
        logging.error(e)
        raise e

    if info and info.status_code != 200:
        raise Exception("上传文件到七牛失败")

    # 返回七牛中保存的图片名，这个图片名也是访问七牛获取图片的路径
    return ret["key"]


if __name__ == '__main__':

    with open('../static/favicon.ico', "rb") as f:
        # print(f.read())
        filename = storage(f.read())
        print(filename)
    pass
