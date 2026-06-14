"""tests/test_adapter.py"""
import pytest
from src.gateway.adapter import Adapter


class TestAdapterABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            Adapter()  # ABC 不能直接实例化

    def test_concrete_subclass_must_implement_methods(self):
        class IncompleteAdapter(Adapter):
            platform = "test"
        with pytest.raises(TypeError):
            IncompleteAdapter()  # 没实现 send 和 start

    def test_full_subclass_works(self):
        class FullAdapter(Adapter):
            platform = "test"
            async def start(self, on_message): pass
            async def send(self, user_id, messages): pass
        a = FullAdapter()
        assert a.platform == "test"
