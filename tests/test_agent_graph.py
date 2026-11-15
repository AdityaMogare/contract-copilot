"""Agent graph control flow with a scripted fake model (design 08 §6). No Azure, no database."""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import FinalAnswer, NOT_FOUND_TEXT, build_graph, history_for_model, validate_final
from app.agent.tools import SourceBook


class FakeAgentModel:
    """bind_tools() → itself; ainvoke() pops scripted AIMessages (repeats the last one forever)."""
    def __init__(self, script): self.script, self.calls = list(script), 0
    def bind_tools(self, tools): return self
    async def ainvoke(self, messages):
        self.calls += 1
        return self.script.pop(0) if len(self.script) > 1 else self.script[0]


class FakeFinalModel:
    def __init__(self, answers): self.answers, self.calls = list(answers), 0
    def with_structured_output(self, *a, **k): return self
    async def ainvoke(self, messages):
        self.calls += 1
        return {"raw": AIMessage(""), "parsed": self.answers.pop(0)}


def _tools(book, fail=False):
    async def search_regulations(query: str) -> str:
        """FAR search."""
        if fail:
            raise RuntimeError("search down")
        sid = book.add("R", {"kind": "regulation", "chunk_id": "6_302-2--000", "citation": "FAR 6.302-2(a)–(d)", "url": "u"})
        return f"[{sid}] FAR 6.302-2 ... one year ..."
    return [StructuredTool.from_function(coroutine=search_regulations, name="search_regulations", description="FAR")]


def _call(n=1):
    return AIMessage("", tool_calls=[{"name": "search_regulations", "args": {"query": f"q{i}"}, "id": f"c{n}-{i}"} for i in range(1)])


def _run(agent, final, book, budget=6, time_budget_s=30.0, fail=False, saver=None, thread="t1", text="question?"):
    usage = []
    g = build_graph(agent, final, _tools(book, fail), book, budget, usage, checkpointer=saver, time_budget_s=time_budget_s)
    cfg = {"configurable": {"thread_id": thread}, "recursion_limit": 40}
    return asyncio.run(g.ainvoke({"messages": [HumanMessage(text)], "tool_calls_used": 0, "final": None}, config=cfg)), usage


def test_tool_then_validated_answer():
    book = SourceBook()
    agent = FakeAgentModel([_call(), AIMessage("done")])
    final = FakeFinalModel([FinalAnswer(status="answered", answer="Limited to one year [R1].", source_ids=["R1"])])
    state, usage = _run(agent, final, book)
    assert state["final"]["status"] == "answered" and state["tool_calls_used"] == 1 and "R1" in book.sources
    assert len(usage) == 3   # 2 agent steps + 1 final


def test_call_budget_forces_final():
    book = SourceBook()
    agent = FakeAgentModel([_call(i) for i in range(10)])           # never stops asking for tools
    final = FakeFinalModel([FinalAnswer(status="answered", answer="x [R1]", source_ids=["R1"])])
    state, _ = _run(agent, final, book, budget=3)
    assert state["tool_calls_used"] == 3 and state["final"]["status"] == "answered"


def test_time_budget_forces_final_without_tools():
    book = SourceBook()
    agent = FakeAgentModel([_call()])
    final = FakeFinalModel([FinalAnswer(status="not_found", answer="", source_ids=[])])
    state, _ = _run(agent, final, book, time_budget_s=0.0)
    assert state["tool_calls_used"] == 0 and state["final"]["answer"] == NOT_FOUND_TEXT


def test_invented_source_ids_retry_then_not_found():
    book = SourceBook()
    agent = FakeAgentModel([_call(), AIMessage("done")])
    bad = FinalAnswer(status="answered", answer="x [D7]", source_ids=["D7"])
    final = FakeFinalModel([bad, bad])
    state, _ = _run(agent, final, book)
    assert state["final"]["status"] == "not_found" and final.calls == 2


def test_failing_tool_is_reported_to_the_model_not_raised():
    book = SourceBook()
    agent = FakeAgentModel([_call(), AIMessage("done")])
    final = FakeFinalModel([FinalAnswer(status="not_found", answer="", source_ids=[])])
    state, _ = _run(agent, final, book, fail=True)
    tool_msgs = [m for m in state["messages"] if m.type == "tool"]
    assert "failed: RuntimeError" in tool_msgs[0].content and state["final"]["status"] == "not_found"


def test_memory_keeps_prior_turns_per_thread():
    saver = InMemorySaver()
    for text in ("first question", "follow-up"):
        book = SourceBook()
        agent = FakeAgentModel([AIMessage("no tools needed")])
        final = FakeFinalModel([FinalAnswer(status="not_found", answer="", source_ids=[])])
        state, _ = _run(agent, final, book, saver=saver, thread="same", text=text)
    humans = [m.content for m in state["messages"] if m.type == "human"]
    assert humans == ["first question", "follow-up"] and state["tool_calls_used"] == 0


def test_history_strips_old_source_markers_and_tool_traffic():
    msgs = [HumanMessage("q1"), _call(), AIMessage("83 awards [D1] and a one-year limit [R1]."), HumanMessage("q2")]
    hist = history_for_model(msgs)
    assert [m.type for m in hist] == ["human", "ai", "human"] and "[D1]" not in hist[1].content


def test_validate_final_rules():
    known = {"R1", "D1"}
    assert validate_final(FinalAnswer(status="answered", answer="x [R1]", source_ids=[]), known) is None
    assert "not returned" in validate_final(FinalAnswer(status="answered", answer="x [C1]", source_ids=[]), known)
    assert "at least one" in validate_final(FinalAnswer(status="answered", answer="x", source_ids=[]), known)


def test_content_filter_detection():
    from app.routers.chat import is_content_filter

    class E(Exception):
        code = "content_filter"
    assert is_content_filter(E("x")) and is_content_filter(RuntimeError("Error code: 400 - content_filter"))
    assert not is_content_filter(RuntimeError("429 Too Many Requests"))
