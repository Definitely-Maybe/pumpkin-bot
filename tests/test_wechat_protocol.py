"""tests/test_wechat_protocol.py"""
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch
from wechat_mcp_server.wechat import WeChatProtocol


class TestXMLParsing:
    def test_parse_text_message(self):
        xml = """<xml>
            <ToUserName>gh_123</ToUserName>
            <FromUserName>openid_abc</FromUserName>
            <CreateTime>1234567890</CreateTime>
            <MsgType>text</MsgType>
            <Content>你好南瓜</Content>
            <MsgId>10001</MsgId>
        </xml>"""
        msg = WeChatProtocol.parse_message(xml)
        assert msg is not None
        assert msg["from_user"] == "openid_abc"
        assert msg["msg_type"] == "text"
        assert msg["content"] == "你好南瓜"

    def test_parse_image_message_returns_unsupported_hint(self):
        xml = """<xml>
            <ToUserName>gh_123</ToUserName>
            <FromUserName>openid_abc</FromUserName>
            <CreateTime>1234567890</CreateTime>
            <MsgType>image</MsgType>
            <PicUrl>http://example.com/pic.jpg</PicUrl>
            <MsgId>10002</MsgId>
        </xml>"""
        msg = WeChatProtocol.parse_message(xml)
        assert msg is not None
        assert msg["msg_type"] == "image"
        assert msg["content"] == "[图片消息——暂不支持]"

    def test_parse_invalid_xml_returns_none(self):
        assert WeChatProtocol.parse_message("<not>xml") is None


class TestSignatureVerification:
    def test_verify_signature_valid(self):
        # 已知正确值：sha1("test123" + "123" + "456") 排序后 = sha1("123456test123")
        import hashlib
        expected = hashlib.sha1("123456test123".encode()).hexdigest()
        result = WeChatProtocol.verify_signature(
            token="test123",
            signature=expected,
            timestamp="123",
            nonce="456",
        )
        assert result is True

    def test_verify_signature_invalid(self):
        result = WeChatProtocol.verify_signature(
            token="test123",
            signature="wrong",
            timestamp="123",
            nonce="456",
        )
        assert result is False


class TestOutgoingText:
    def test_normalize_literal_unicode_escapes(self):
        text = r"\u4f60\u597d \u4e16\u754c"
        assert WeChatProtocol.normalize_outgoing_text(text) == "你好 世界"

    def test_normalize_keeps_plain_chinese(self):
        assert WeChatProtocol.normalize_outgoing_text("你好 世界") == "你好 世界"
