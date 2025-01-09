from stock_hunter import update_stock 
import time

def main():
    print("main 当前执行时间：", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    table_name_stock = "指数样本跟踪"
    weibo_user = [
        '财富秘钥', 
        '专业证券分析',
        # '倩男游神'
        ]
    update_stock(table_name_stock, weibo_user)

if __name__ == "__main__":
    # 每5分钟运行一次main()
    while True:
        main()
        time.sleep(600)  # 间隔10分钟