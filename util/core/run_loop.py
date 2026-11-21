"""多用户运行循环编排。

把「逐用户：重置状态 → 处理 → 下一个人」的循环骨架独立出来；每用户的具体
处理抛异常时中断循环，交由调用方统一捕获（finally 中仍会生成汇总/释放锁）。"""

from __future__ import annotations


def run_users(
    user_config_list,
    *,
    before_each,
    process,
    after_all=None,
    should_stop=None,
) -> None:
    """依次对每个用户执行 before_each + process；全部完成后执行 after_all。

    ``should_stop`` 返回 True 时不再处理后续用户（如本轮已命中风控）。
    """
    for user_config in user_config_list:
        if should_stop is not None and should_stop():
            break
        before_each(user_config)
        process(user_config)
    if after_all is not None:
        after_all()
