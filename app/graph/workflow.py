from __future__ import annotations

from contextlib import ExitStack

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import fail_node, finalize_node, run_parent_agent_factory
from app.graph.state import IncidentState


def build_graph(llm):
    builder = StateGraph(IncidentState)

    builder.add_node("run_parent_agent", run_parent_agent_factory(llm))
    builder.add_node("finalize", finalize_node)
    builder.add_node("fail", fail_node)

    builder.add_edge(START, "run_parent_agent")

    builder.add_conditional_edges(
        "run_parent_agent",
        lambda s: s.get("next_route", "loop"),
        {
            "loop": "run_parent_agent",
            "finalize": "finalize",
            "fail": "fail",
        },
    )

    builder.add_edge("finalize", END)
    builder.add_edge("fail", END)

    return builder


def compile_graph(llm, db_url: str = "sqlite:///./agent_state.db"):
    # Keep the SqliteSaver context alive for as long as the compiled graph is in use.
    conn_string = db_url
    if conn_string.startswith("sqlite:///"):
        conn_string = conn_string.replace("sqlite:///", "", 1)

    stack = ExitStack()
    checkpointer = stack.enter_context(SqliteSaver.from_conn_string(conn_string))
    graph = build_graph(llm).compile(checkpointer=checkpointer)
    graph._checkpoint_stack = stack  # noqa: SLF001
    return graph

