"""tests/test_wechat_queue.py"""
from wechat_mcp_server.queue import MessageQueue


class TestMessageQueue:
    def test_push_and_poll_new_messages(self):
        mq = MessageQueue()
        mq.push("openid_1", "text", "你好", "123")
        msgs = mq.poll("openid_1")
        assert len(msgs) == 1
        assert msgs[0]["user_openid"] == "openid_1"
        assert msgs[0]["content"] == "你好"

    def test_poll_only_returns_new_since_last_poll(self):
        mq = MessageQueue()
        mq.push("openid_1", "text", "msg1", "1")
        mq.poll("openid_1")  # consume
        mq.push("openid_1", "text", "msg2", "2")
        msgs = mq.poll("openid_1")
        assert len(msgs) == 1
        assert msgs[0]["content"] == "msg2"

    def test_different_users_independent_cursors(self):
        mq = MessageQueue()
        mq.push("openid_1", "text", "a", "1")
        mq.push("openid_2", "text", "b", "2")
        mq.poll("openid_1")
        msgs_2 = mq.poll("openid_2")
        assert len(msgs_2) == 1
        assert msgs_2[0]["content"] == "b"

    def test_max_length_enforced(self):
        mq = MessageQueue(maxlen=3)
        for i in range(5):
            mq.push("u", "text", f"msg{i}", str(i))
        msgs = mq.poll("u")
        # 旧消息被丢弃，只剩最近 maxlen 条
        assert len(msgs) <= 3
        contents = [m["content"] for m in msgs]
        assert "msg0" not in contents

    def test_poll_empty_returns_empty_list(self):
        mq = MessageQueue()
        assert mq.poll("unknown_user") == []

    def test_queue_size_reported(self):
        mq = MessageQueue(maxlen=10)
        mq.push("a", "text", "x", "1")
        mq.push("b", "text", "y", "2")
        assert mq.size == 2
