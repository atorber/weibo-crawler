'''
解析微博，获取指数样本，并更新到云文档
'''

from stock_hunter import update_stock_to_cloud
import time


def main():
    # 每5分钟运行一次main()
    while True:
        print("main 当前执行时间：", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))  # noqa:501
        table_name_stock = "指数样本跟踪"
        weibo_user = [
            "财富秘钥",
            "专业证券分析",
            # '倩男游神'
        ]
        update_stock_to_cloud(table_name_stock, weibo_user)
        time.sleep(600)  # 间隔10分钟


if __name__ == "__main__":
    main()
