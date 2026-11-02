"""LangGraph agent that answers "have I seen this error before?" with citations.

Planned responsibility (Phase 5): graph state, nodes, prompts and the ``StateGraph`` implementing
parse -> normalize/fingerprint -> exact match -> hybrid retrieve -> grade relevance -> corrective
loop (query rewrite / external search, bounded) -> cited generation -> citation verification ->
answer or honest abstention.
"""
