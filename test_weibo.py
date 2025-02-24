from stock_hunter import get_weibos, call_openai_api
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    created_at = "2025-02-21 15:00:00"
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
    你的投资理念是选赛道、精选股、做减法，即选准赛道在看好的方向选择优质股票再结合市场表现进一步缩减最终选出交易的股票
    基础股票池：主要用户观察行情、板块趋势,初选股票
    精选股票池:重点关注的股票
    交易股票池：从精选股票池中选择龙头股票进行交易
    股票池中的股票相应标注纳入股票池的原因和逻辑
    请根据微博内容整理出基础股票池、精选股票池和交易股票池
    '''
    response = call_openai_api(all_weibos, system_prompt)
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
