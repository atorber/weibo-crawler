from stock_hunter import get_weibos, call_openai_api  # noqa: E402,F401
import logging
from datetime import datetime
import os
import logging.config
import time
from datetime import datetime, timedelta
from lark import LarkAPI

# 引入环境变量
from dotenv import load_dotenv

load_dotenv()

app_id = os.getenv("app_id")
app_secret = os.getenv("app_secret")
app_token = os.getenv("app_token")
api = LarkAPI(app_id, app_secret, app_token)
table_id_weibo = api.get_table_id("微博")

def setup_logging():
    """设置并初始化日志系统"""
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(current_dir, "log")
    logging_path = os.path.join(current_dir, "logging.conf")

    # 确保日志目录存在
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        print(f"创建日志目录: {log_dir}")

    # 检查配置文件是否存在
    if not os.path.exists(logging_path):
        raise FileNotFoundError(
            f"日志配置文件 {logging_path} 不存在，请确认：\n"
            "1. 在项目根目录创建logging.conf文件\n"
            "2. 文件路径是否正确"
        )

    # 初始化日志配置
    logging.config.fileConfig(logging_path)
    return logging.getLogger("api")

# 删除原有的日志相关代码，使用新的setup_logging函数
logger = setup_logging()

def main():
    # 当前日期的前一天
    today = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    # today = '2025-02-23'
    created_at = today + ' 09:00:00'
    print('当前日期为%s' % today)
    print('当前时间为%s' % created_at)
    weibos = get_weibos(created_at=created_at)
    print('获取微博成功', len(weibos))

    # 汇总拼接全部微博
    all_weibos = ''
    for weibo in weibos:
        all_weibos += weibo['created_at'] + ' ' + weibo['text'] + '\n'

    # 打印微博内容
    print(all_weibos)
    print('微博内容拼接成功,微博数量为%s,微博内容长度为%s' % (len(weibos), len(all_weibos)))

    # 调用openai api
    system_prompt = '''
你是一个资深股票投资基金经理，擅长通过研报信息挖掘暴涨牛股，你能够从研报信息中整理出基础股票池、精选股票池和交易股票池。
你的投资理念是“选赛道、精选股、做减法”，即选准赛道在看好的方向选择优质股票再结合市场表现进一步缩减最终选出交易的股票

- 股票池定义：
1. 基础股票池：主要用户观察行情、板块趋势,初选股票,纳入研报中提及的所有股票
2. 精选股票池:从基础股票池选择重点关注的股票，精选股票池结合上市公司的业绩、行业地位、市场表现、多个研报提及等指标筛选
3. 交易股票池：从精选股票池中选择最优可能上涨的股票进行交易

- 要求：
1. 基础股票池中的股票需要覆盖研报中提及的全部A股股票，按主题和板块分类，主题进包括AI算力、AI+、机器人、AI眼镜等相关主题，其他主题的股票不纳入股票池
2. 精选股票池、交易股票池股票需要标注纳入股票池的原因和逻辑
4. 精选股票池从基础股票池中选取不超过30只，交易股票池从精选股票池中选取不超过10只

- 限制
1. 输出是不使用表格、不使用markdown格式，输出内容为纯文本，可以直接被作为新浪微博文本发布
2. 不能编造研报原文中没有提及的股票
3. 不能遗漏研报中提及的任何一只股票

- 输出格式

💹 交易股票池

<股票1>：<主题>，<原因和逻辑>

✨ 精选股票池

<股票1>：<主题>，<原因和逻辑>

📦 基础股票池

【主题名称1>】：<股票1>、<股票2>

【主题名称2】：<股票3>、<股票4>

策略说明：<策略的说明>
风险提示：<风险提示>'''

    full_prompt = system_prompt + '\n' + all_weibos

    logger.info(full_prompt)
    # 调用openai api
    # response = call_openai_api(all_weibos, system_prompt)
    # logger.info(response.choices[0].message.content)

    weibo_update = {
        "user_id": "1234567890",
        "screen_name": "研报猎手",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "text": full_prompt
    }
    api.add_record(table_id_weibo, weibo_update)
    logging.info("保存微博到云端成功")

if __name__ == "__main__":

    main()

    # # 每天上午9:00周期执行一次
    # last_run_date = None
    # while True:
    #     now = datetime.now()
    #     current_date = now.date()
        
    #     # 检查是否是上午9点且今天还没有运行过
    #     if now.hour == 9 and current_date != last_run_date:
    #         logger.info(f"开始执行每日任务，当前时间: {now}")
    #         main()
    #         last_run_date = current_date
    #         logger.info(f"任务执行完成，下次执行时间: {(current_date + timedelta(days=1)).strftime('%Y-%m-%d')} 09:00:00")
    #     else:
    #         logger.info(f"当前时间: {now}, 不在执行时间范围内") 
    #     # 每分钟检查一次
    #     time.sleep(60)
