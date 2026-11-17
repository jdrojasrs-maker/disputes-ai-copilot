from disputes.llm.client import LLMClient


class _HasComplete:
    async def complete(self, request):
        raise NotImplementedError


class _WithoutComplete:
    async def send(self, request):
        raise NotImplementedError


def test_a_class_with_a_complete_method_is_an_llm_client() -> None:
    assert isinstance(_HasComplete(), LLMClient)


def test_a_class_without_a_complete_method_is_not_an_llm_client() -> None:
    assert not isinstance(_WithoutComplete(), LLMClient)
