# -*- coding: utf-8 -*-
# flake8: noqa: E501
import lark_oapi as lark
import json
import os
import time
from dotenv import load_dotenv
import functools
import random
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
load_dotenv()


# 修改重试装饰器的配置
def lark_retry_decorator(func):
    @functools.wraps(func)
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=1, max=60),
        reraise=True,
        # 扩展需要重试的异常类型，包含SSL相关错误
        retry=retry_if_exception_type((
            requests.exceptions.RequestException,
            json.JSONDecodeError,
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError
        ))
    )
    def wrapper(*args, **kwargs):
        try:
            response = func(*args, **kwargs)
            if not response.success():
                raise Exception(f"API request failed: {response.code}, {response.msg}")
            # 增加随机延时范围
            time.sleep(random.uniform(1, 3))
            return response
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            print(f"SSL/Connection error occurred: {str(e)}, retrying...")
            time.sleep(random.uniform(3, 5))  # SSL错误时增加额外等待时间
            raise
        except Exception as e:
            print(f"Request failed: {str(e)}, retrying...")
            raise
    return wrapper

class LarkAPI:

    tables = {}

    def __init__(self, app_id, app_secret, app_token):
        # 添加SSL验证配置
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
        self.app_token = app_token
        self.tables = self.get_tables()
        # self.table_id = self.get_table_id()

    def get_tables(self):
        request = lark.BaseRequest.builder() \
            .http_method(lark.HttpMethod.GET) \
            .uri(f"/open-apis/bitable/v1/apps/{self.app_token}/tables") \
            .token_types({lark.AccessTokenType.TENANT}) \
            .build()
        response = self.client.request(request)
        if not response.success():
            lark.logger.error(
                f"client.request failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
        tablesRaw = json.loads(response.raw.content)['data']['items']

        for table in tablesRaw:
            self.tables[table['name']] = table['table_id']

        return self.tables

    def get_table_id(self, name):
        return self.tables[name]

    def add_record(self, table_id, fields):
        body = {
            "fields": fields
        }
        request = lark.BaseRequest.builder() \
            .http_method(lark.HttpMethod.POST) \
            .uri(f"/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records") \
            .token_types({lark.AccessTokenType.TENANT}) \
            .body(body) \
            .build()
        response = self.client.request(request)
        if not response.success():
            lark.logger.error(
                f"client.request failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
        # lark.logger.info(str(response.raw.content, lark.UTF_8))
        return response
    
    @lark_retry_decorator
    def get_records(self, table_id, page_token=None):
        query = {"page_size": "500"}
        if page_token:
            query['page_token'] = page_token
            # query = {"page_token": page_token}
        print('query:', query)
        request = lark.BaseRequest.builder() \
            .http_method(lark.HttpMethod.POST) \
            .uri(f"/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/search") \
            .token_types({lark.AccessTokenType.TENANT}) \
            .queries(query) \
            .body({}) \
            .build()
        response = self.client.request(request)
        print('get_records response has_more:', json.loads(response.raw.content)['data']['has_more'])
        # print('get_records response page_token:', json.loads(response.raw.content)['data']['page_token'])
        print('get_records response:', len(json.loads(response.raw.content)['data']['items']))
        if not response.success():
            lark.logger.error(
                f"client.request failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
        # lark.logger.info(str(response.raw.content, lark.UTF_8))
        return response
    
    def get_records_all(self, table_id):
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                page_token_all = []
                response_all = []
                response = self.get_records(table_id)
                # print('get_records_all response:', response)
                if not response.success():
                    lark.logger.error(
                        f"client.request failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
                # lark.logger.info(str(response.raw.content, lark.UTF_8))

                response_all.append(json.loads(response.raw.content)['data']['items'])

                has_more = json.loads(response.raw.content)['data']['has_more']
                time.sleep(1)
                if has_more:
                    page_token = json.loads(response.raw.content)['data']['page_token']

                    while has_more and page_token not in page_token_all:
                        response_next = self.get_records(table_id, page_token)
                        page_token_all.append(page_token)
                        if not response_next.success():
                            lark.logger.error(
                                f"client.request failed, code: {response_next.code}, msg: {response_next.msg}, log_id: {response_next.get_log_id()}")
                        has_more = json.loads(response_next.raw.content)['data']['has_more']
                        time.sleep(1)
                        if has_more:
                            page_token = json.loads(response_next.raw.content)['data']['page_token']
                        
                        response_all.append(json.loads(response_next.raw.content)['data']['items'])

                all_records = []  
                for all_records_raw in response_all:
                    for record in all_records_raw:
                        fields = {}
                        # fields['_id'] = record['record_id']
                        fields_raw = record['fields']
                        for field in fields_raw:
                            # print('field:', field)
                            # fields_raw[field]的数据类型
                            field_type = type(fields_raw[field])
                            # print('field_type:', field_type)

                            is_text = True if (field_type == list and 'type' in fields_raw[field][0]) else False
                            is_dict = True if field_type == dict else False
                            if is_text:
                                fields[field] = fields_raw[field][0]['text']
                            elif is_dict and 'type' in fields_raw[field]:
                                pass
                            else:
                                fields[field] = fields_raw[field]
                        record['fields'] = fields
                        all_records.append(record)
                # print('all_records:', all_records)
                return all_records
            except Exception as e:
                if attempt == max_attempts - 1:  # 最后一次尝试
                    print(f"Failed to get records after {max_attempts} attempts: {str(e)}")
                    return []
                print(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(random.uniform(5, 10))  # 在重试之前等待

    @lark_retry_decorator
    def batch_update_records(self, table_id, records):
        # 添加批量处理限制 
        BATCH_SIZE = 500
        responses = []

        if 'record_id' not in records[0]:
            records = [{
                "record_id": r.pop('_id'),
                "fields": r
            } for r in records]

        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]
            body = {"records": batch}
            
            request = lark.BaseRequest.builder() \
                .http_method(lark.HttpMethod.POST) \
                .uri(f"/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update") \
                .token_types({lark.AccessTokenType.TENANT}) \
                .body(body) \
                .build()
            response = self.client.request(request)
            responses.append(response)

        return responses[-1]

    @lark_retry_decorator 
    def batch_add_records(self, table_id, records):
        # 添加批量处理限制
        BATCH_SIZE = 500
        responses = []
        
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]
            new_records = [{"fields": record} for record in batch]
            
            body = {"records": new_records}
            request = lark.BaseRequest.builder() \
                .http_method(lark.HttpMethod.POST) \
                .uri(f"/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create") \
                .token_types({lark.AccessTokenType.TENANT}) \
                .body(body) \
                .build()
            response = self.client.request(request)
            responses.append(response)
            
        return responses[-1] # 返回最后一个响应

# 使用示例
if __name__ == "__main__":
    app_id = os.getenv("app_id")
    app_secret = os.getenv("app_secret")
    app_token = os.getenv("app_token")
    api = LarkAPI(app_id, app_secret, app_token)
    # table_id_1 = api.get_table_id("H表现分析")
    # table_id_2 = api.get_table_id("数据表2")
    # while True:
    #     update_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    #     power, total_assets, market_val, update_a = 100, 50, 1000, update_at
    #     fields = {
    #         "最大购买力": power,
    #         "总资产净值": total_assets,
    #         "持仓": market_val,
    #         "更新时间": update_at
    #     }
    #     api.add_record(table_id_1, fields)
    #     api.add_record(table_id_2, fields)
    #     time.sleep(60)
    table_id_1 = api.get_table_id("A表现分析")
    time.sleep(1)
    rl = api.get_records_all(table_id_1)
    print(json.dumps(rl, indent=4, ensure_ascii=False))

    table_id_1 = api.get_table_id("进出记录")
    time.sleep(1)
    rl = api.get_records_all(table_id_1)
    print(json.dumps(rl, indent=4, ensure_ascii=False))

    # table_id_2 = api.get_table_id("指数样本跟踪")
    # rl2 = api.get_records_all(table_id_2)

    # for r in rl:
    #     name = r['名称']
    #     if name != '初始资产':
    #         # 从rl2中查找 名称 为 中无人机 对应的记录
    #         stock = [stock for stock in rl2 if stock['名称'] == r['名称']]
    #         print(stock[0])
    #         r['代码'] = stock[0]['代码']
    #         print(r)
    # print(rl)
    # api.batch_update_records(table_id_1, rl)
