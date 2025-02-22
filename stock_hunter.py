# noqa: E501
import logging
import logging.config
import os
import sqlite3
import json
from openai import OpenAI
import time
from lark import LarkAPI

# 引入环境变量
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("log/app_pro.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

# 延时
app_id = os.getenv("app_id")
app_secret = os.getenv("app_secret")
app_token = os.getenv("app_token")
api = LarkAPI(app_id, app_secret, app_token)
table_id_blacklist = api.get_table_id("黑名单")
time.sleep(2)
table_id_weibo = api.get_table_id("微博")
time.sleep(2)
DATABASE_PATH = "./weibo/weibodata.db"
# 打印数据库文件路径,用于调试和确认数据库位置
logging.info("数据库文件路径: %s", DATABASE_PATH)


# 调用OpenAI API生成文本
def call_openai_api(text, system_prompt=None):
    """调用OpenAI API生成文本"""
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_API_URL")
    model = os.getenv("OPENAI_MODEL")
    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        if system_prompt:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
            )
        else:
            completion = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": text}]
            )
        logging.info(completion)
        return completion.choices[0].message.content
    except Exception as e:
        logging.exception("OpenAI API调用失败", e)
        return "生成文本时出错。"


# 从文本中找出股票名称
def get_stock_data(text):
    """使用gpt从文本中找出股票名称"""
    system_prompt = """
    你是一个股票分析专家擅长从研报中提取关键股票信息
    1. 你需要从下面的文本中找出文本中包含的股票名称和概念标签
    2. 尽可能从文本中找到股票的概念标签，如果没有标签不需要编造
    3. 文本中对行业、方向、概念的描述也可以作为标签
    4. 如果确定是港股，需要添加<港股>作为标签
    5. 请将找到的股票名称和标签按照股票名称:标签的格式返回

    有股票信息时的返回如下文本格式JSON格式（必须以"{"开头，以"}"结束，且不包含任何markdown格式）,示例：
    {
    "万兴科技": [
        "文生视频",
        "Sora"
    ],
    "科大讯飞": [
        "大语言模型",
        "Sora"
    ]}

    没有股票信息的返回如下格式：
    {}
    """
    response = call_openai_api(text, system_prompt)
    return response


# 获取微博
def get_weibos():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        # 按created_at倒序查询所有微博
        cursor.execute("SELECT * FROM weibo ORDER BY created_at DESC")
        columns = [column[0] for column in cursor.description]
        weibos = []
        for row in cursor.fetchall():
            weibo = dict(zip(columns, row))
            weibos.append(weibo)
        conn.close()
        return weibos
    except Exception as e:
        logging.exception(e)
        return {"error": str(e)}


# 获取所有股票
def get_stocks(weibo_user=None):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        # 按created_at倒序查询所有微博
        if weibo_user is not None:
            # weibo_user示例：['财富秘钥', '专业证券分析']
            query = (
                "SELECT * FROM stock WHERE screen_name IN ({})"
                "ORDER BY created_at DESC"
                ).format(
                ", ".join("?" * len(weibo_user))
            )
            cursor.execute(query, weibo_user)
        else:
            cursor.execute("SELECT * FROM stock ORDER BY created_at DESC")
        columns = [column[0] for column in cursor.description]
        stocks = []
        for row in cursor.fetchall():
            stock = dict(zip(columns, row))
            stocks.append(stock)
        conn.close()
        return stocks
    except Exception as e:
        logging.exception(e)
        return {"error": str(e)}


# 添加股票
def add_stocks(data):
    stock = data if data else None
    logging.info(stock)
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        # 转换data对象，写入表，返回写入结果
        table = "stock"
        keys = ", ".join(stock.keys())
        values = ", ".join(["?"] * len(stock))
        sql = """INSERT OR REPLACE INTO {table}({keys}) VALUES({values})
                """.format(
            table=table, keys=keys, values=values
        )
        cursor.execute(sql, list(stock.values()))
        conn.commit()
        conn.close()
        res = {"message": "Stock added successfully", "stock": stock}
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        logging.exception(e)
        return {"error": str(e)}


# 获取股票详情
def get_stock(id):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        # 按id查询微博
        cursor.execute("SELECT * FROM stock WHERE id=?", (id,))
        columns = [column[0] for column in cursor.description]
        stock = dict(zip(columns, cursor.fetchone()))
        conn.close()
        return stock
    except Exception as e:
        logging.exception(e)
        return {"error": "Stock not found"}


# 更新股票
def update_stock(id, stock):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        # 按id更新微博
        cursor.execute("UPDATE stock SET text=? WHERE id=?", (stock["text"], id))  # noqa: E501
        conn.commit()
        conn.close()
        return {"message": "Stock updated successfully"}
    except Exception as e:
        logging.exception(e)
        return {"error": "Stock not found"}


# 删除股票
def del_stock(id):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        # 按id删除微博
        cursor.execute("DELETE FROM stock WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return {"message": "Stock deleted successfully"}
    except Exception as e:
        logging.exception(e)
        return {"error": "Stock not found"}


# 微博文本中查找股票
def find_stock(weibo, retry_count=0):
    logging.info("开始查找股票，第%d次", retry_count)
    if retry_count >= 5:
        logging.error("重试次数超过5次，放弃处理")
        weibo["text"] = "{}"
        weibo["attitudes_count"] = 0
        # 将微博解析结果标记到数据库
        res = add_stocks(weibo)
        logging.info("标记结果 %s", res)
        return

    text = weibo["text"]
    res = get_stock_data(text)
    logging.info("微博解析结果：%s", res)

    if "{}" in res:
        logging.info("解析结果为空，将微博文本设置为空")
        # 如果解析结果为空，则将微博文本设置为空
        weibo["text"] = "{}"
        weibo["attitudes_count"] = 0
        logging.info(weibo)
        res = add_stocks(weibo)
        logging.info("标记结果成功 %s", res)
    else:
        try:
            res = res.replace("```json", "").replace("```", "")
            res_json = json.loads(res)
            logging.info("解析为JSON成功 %s", res_json)

            if res_json != {}:
                logging.info("不是空JSON，微博保存到云端")
                weibo_update = weibo
                weibo_update["text"] = res
                weibo_update["article_url"] = text
                api.add_record(table_id_weibo, weibo_update)
                logging.info("保存微博到云端成功")

                for stock in res_json.keys():
                    item = res_json[stock]
                    item.append(weibo["screen_name"])
                    res_json[stock] = item
                weibo["text"] = json.dumps(res_json, ensure_ascii=False)
                weibo["attitudes_count"] = len(res_json.keys())
            else:
                weibo["text"] = res
                weibo["attitudes_count"] = 0
            logging.info(weibo)
            # 将微博解析结果标记到数据库
            logging.info("将微博解析结果标记到数据库")
            res = add_stocks(weibo)
            logging.info("标记结果成功 %s", res)

        except Exception as e:
            logging.error("解析为JSON失败, 重新解析 %s", e)
            time.sleep(3)
            find_stock(weibo, retry_count + 1)


# 统计stock表中的数据
def count_stock(weibo_user):
    stocks = get_stocks(weibo_user)
    logging.info("获取全部已解析微博：%d", len(stocks))
    logging.info(stocks)
    table = {}
    for stock in stocks:
        text = stock["text"]
        logging.info("解析结果：%s", text)
        res = json.loads(text)
        for key in res.keys():
            if key in table.keys():
                table[key] += 1
            else:
                table[key] = 1
    return table


# 统计stock表中的数据
def tag_stock(weibo_user):
    stocks = get_stocks(weibo_user)
    table = {}
    for stock in stocks:
        text = stock["text"]
        res = json.loads(text)
        for key in res.keys():
            item = res[key]
            for tag in item:
                if tag in table.keys():
                    if key not in table[tag]:
                        table[tag].append(key)
                else:
                    table[tag] = [key]
    return table


def stock_tag(weibo_user):
    stocks = get_stocks(weibo_user)
    table = {}
    for stock in stocks:
        text = stock["text"]
        res = json.loads(text)
        for key in res.keys():
            item = res[key]
            for tag in item:
                if key in table.keys():
                    if tag not in table[key]:
                        table[key].append(tag)
                else:
                    table[key] = [tag]
    return table


def get_blacklist(table_id_blacklist):
    all_blacklist_response = api.get_records(table_id_blacklist)
    all_blacklist_items = json.loads(all_blacklist_response.raw.content)[
        "data"]["items"]
    blacklist = []
    blacklist_map = {}
    for record in all_blacklist_items:
        fields_raw = record["fields"]
        name = fields_raw["名称"][0]["text"]
        code = fields_raw["代码"][0]["text"] if "代码" in fields_raw.keys() else ""
        if code != "":
            blacklist_map[name] = code
        blacklist.append(name)
    return blacklist, blacklist_map


def update_stock_to_cloud(table_name_stock, weibo_user=None):

    table_id_stock = api.get_table_id(table_name_stock)

    weibos = get_weibos()
    logging.info("从数据库获取全部微博：%d", len(weibos))
    # logging.info(weibos)

    stocks = get_stocks()
    logging.info("从数据库获取全部已解析微博：%d", len(stocks))
    # logging.info(stocks)

    # 遍历weibos，如果stock表中没有该微博，则添加
    for weibo in weibos:
        # logging.info('微博信息：%s', json.dumps(weibo, ensure_ascii=False))
        id = weibo["id"]
        stock_old = get_stock(id)
        logging.info("从数据库查询微博结果 %s", stock_old)

        if stock_old.get("error") is not None:
            logging.info("数据库中不存在记录，微博未被解析：%s", id)
            find_stock(weibo)
            logging.info("查找股票成功")
            time.sleep(1)
        else:
            logging.info("数据库中存在记录，微博已解析：%s", id)
            # 尝试json.loads(stock_old['text'])，如果text不是json格式，则更新text为{}
            try:
                res = json.loads(stock_old["text"])
                logging.info("将数据库中保存的解析结果转换为JSON成功 %s", res)
            except Exception as e:
                logging.error("将数据库中保存的解析结果转换为JSON失败 %s", e)
                stock_old["text"] = "{}"
                time.sleep(1)
                update_stock(id, stock_old)
                logging.info("更新数据库微博解析记录成功")

    table1 = count_stock(weibo_user)
    logging.info("统计结果：%s", json.dumps(table1, ensure_ascii=False))

    table2 = tag_stock(weibo_user)
    logging.info("标签结果：%s", json.dumps(table2, ensure_ascii=False))

    table3 = stock_tag(weibo_user)
    logging.info("股票标签：%s", json.dumps(table3, ensure_ascii=False))

    # 获取黑名单
    logging.info("从云端获取黑名单")
    blacklist, blacklist_map = get_blacklist(table_id_blacklist)
    logging.info("黑名单：%s", blacklist)
    logging.info("黑名单映射：%s", blacklist_map)

    # 获取云端股票
    all_records_items = api.get_records_all(table_id_stock)
    logging.info("从云端股票表获取全部股票：%d", len(all_records_items))

    all_names = []
    all_records_raw = {}

    for record in all_records_items:
        fields = {}
        fields_raw = record["fields"]
        if "名称" not in fields_raw.keys():
            continue
        name = fields_raw["名称"]
        all_names.append(name)
        all_records_raw[name] = record
    # logging.info('all_names: %s', all_names)
    # logging.info('all_records: %s', all_records_raw)

    new_records = []
    new_records_code = []
    stock = {}
    new_stocks = []
    for key in table3.keys():
        tag = table3[key]
        name = key
        if key in blacklist:
            logging.info("黑名单：%s", key)
            new_name = blacklist_map[key] if key in blacklist_map.keys() else None  # noqa: E501
            if new_name is not None:
                name = new_name
            else:
                continue

        if name not in all_names:
            logging.info("云端不存在股票：%s", name)
            stock = {"名称": name, "标签": tag, "热度": table1[key]}
            logging.info("向云端添加记录名称：%s", name)
            logging.info("向云端添加记录：%s", stock)
            if name not in new_records_code:
                new_records_code.append(name)
                # api.add_record(table_id_stock, stock)
                stock['最后提及时间'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())  # noqa: E501
                new_stocks.append(stock)
        else:
            logging.info("stock在云端已存在：%s", name)
            record = all_records_raw[name]
            # 合并标签
            old_tag = (
                record["fields"]["标签"] if "标签" in record["fields"].keys() else []  # noqa: E501
            )
            tag = old_tag + tag
            # 移除screen_name标签
            tag = [x for x in tag if x != "screen_name"]
            # 去重
            tag = list(set(tag))

            fields = {"名称": name, "标签": tag, "热度": table1[key]}
            fields['最后提及时间'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())  # noqa: E501
            logging.info("更新云端股票记录：%s", fields)
            new_record = {"record_id": record["record_id"], "fields": fields}
            new_records.append(new_record)

    if len(new_stocks) > 0:
        # new_holdings分片添加，每次500条
        for i in range(0, len(new_stocks), 500):
            api.batch_add_records(table_id_stock, new_stocks[i: i + 500])
            time.sleep(0.2)
        logging.info("向云端添加记录：%d", len(new_stocks))
    else:
        logging.info("无需向云端添加记录")

    if len(new_records) > 0:
        api.batch_update_records(table_id_stock, new_records)
        logging.info("更新云端股票记录：%d", len(new_records))
    else:
        logging.info("无需更新云端股票记录")


if __name__ == "__main__":

    table_name_stock = "精选跟踪"
    weibo_user = [
        # '财富秘钥',
        # '专业证券分析',
        "倩男游神"
    ]
    update_stock_to_cloud(table_name_stock, weibo_user)
