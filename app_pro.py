from stock_hunter import update_stock 

def main():
    table_name_stock = "精选跟踪"
    weibo_user = [
        # '财富秘钥', 
        # '专业证券分析',
        '倩男游神'
        ]
    update_stock(table_name_stock, weibo_user)

if __name__ == "__main__":
    main()