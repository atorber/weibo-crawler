# -*- coding: utf-8 -*-
# flake8: noqa: E501
import lark_oapi as lark
import json
import os
import time
from dotenv import load_dotenv
load_dotenv()


class LarkAPI:
    def __init__(self, app_id, app_secret, app_token):
        self.client = lark.Client.builder().app_id(app_id)\
            .app_secret(app_secret)\
            .log_level(lark.LogLevel.INFO).build()
        self.app_token = app_token
        # self.table_id = self.get_table_id()

    def get_table_id(self, name):
        request = lark.BaseRequest.builder() \
            .http_method(lark.HttpMethod.GET) \
            .uri(f"/open-apis/bitable/v1/apps/{self.app_token}/tables") \
            .token_types({lark.AccessTokenType.TENANT}) \
            .build()
        response = self.client.request(request)
        if not response.success():
            lark.logger.error(
                f"client.request failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
            return ''
        tables = json.loads(response.raw.content)['data']['items']
        for table in tables:
            if table['name'] == name:
                return table['table_id']
        return ''

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
    
    def  batch_add_records(self, table_id, records):
        new_records = []
        for record in records:
            new_records.append({
                "fields": record
            })
        body = {
            "records": new_records
        }
        request = lark.BaseRequest.builder() \
            .http_method(lark.HttpMethod.POST) \
            .uri(f"/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create") \
            .token_types({lark.AccessTokenType.TENANT}) \
            .body(body) \
            .build()
        response = self.client.request(request)
        if not response.success():
            lark.logger.error(
                f"client.request failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
        # lark.logger.info(str(response.raw.content, lark.UTF_8))
        return response

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
                time.sleep(1)
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
    
    def batch_update_records(self, table_id, records):

        if 'record_id' not in records[0]:
            new_records = []
            for record in records:
                record_id = record['_id']
                del record['_id']
                new_records.append({
                    "record_id": record_id,
                    "fields": record
                })
            records = new_records
        body = {
            "records": records
        }
        request = lark.BaseRequest.builder() \
            .http_method(lark.HttpMethod.POST) \
            .uri(f"/open-apis/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update") \
            .token_types({lark.AccessTokenType.TENANT}) \
            .body(body) \
            .build()
        response = self.client.request(request)
        if not response.success():
            lark.logger.error(
                f"client.request failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")
        # lark.logger.info(str(response.raw.content, lark.UTF_8))
        return response

# 使用示例
if __name__ == "__main__":
    app_id = os.getenv("app_id")
    app_secret = os.getenv("app_secret")
    app_token = os.getenv("app_token")
    api = LarkAPI(app_id, app_secret, app_token)
    # table_id_1 = api.get_table_id("数据表1")
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
    table_id_1 = api.get_table_id("表现分析")
    rl = api.get_records_all(table_id_1)
    print(json.dumps(rl, indent=4, ensure_ascii=False))

    table_id_1 = api.get_table_id("进出记录")
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
