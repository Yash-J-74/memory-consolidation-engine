import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from api_client import (
    fetch_active_memories,
    fetch_conflicts,
    fetch_memory_history,
    fetch_session_trace,
    fetch_threshold_sweep,
    ingest_session_result,
)


st.set_page_config(page_title="Memory Consolidation Engine", layout="wide")


def _ensure_session_defaults() -> None:
    defaults = {
        "user_id": "user_001",
        "active_session_id": None,
        "last_ingestion_result": None,
        "sweep_results": None,
        "batch_sessions": [],
        "batch_traces": {},
        "last_batch_result": None,
        "last_batch_errors": [],
        "data_errors": {},
        "memories": [],
        "history": [],
        "conflicts": [],
        "trace": None,
        "data_loaded": False,
        "_last_user_id": None,
        "_last_session_id": None,
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _set_error(key: str, value):
    st.session_state.data_errors[key] = value


def _load_list_result(result, state_key: str, error_key: str) -> None:
    if result.get("ok") and isinstance(result.get("data"), list):
        st.session_state[state_key] = result["data"]
        _set_error(error_key, None)
    else:
        st.session_state[state_key] = []
        _set_error(error_key, result.get("error") or "No data returned from backend.")


def _load_dict_result(result, state_key: str, error_key: str) -> None:
    if result.get("ok") and isinstance(result.get("data"), dict):
        st.session_state[state_key] = result["data"]
        _set_error(error_key, None)
    else:
        st.session_state[state_key] = None
        _set_error(error_key, result.get("error") or "No data returned from backend.")


def reset_user_state() -> None:
    st.session_state.memories = []
    st.session_state.history = []
    st.session_state.conflicts = []
    st.session_state.trace = None
    st.session_state.active_session_id = None
    st.session_state.last_ingestion_result = None
    st.session_state.sweep_results = None
    st.session_state.batch_sessions = []
    st.session_state.batch_traces = {}
    st.session_state.last_batch_result = None
    st.session_state.last_batch_errors = []
    st.session_state.data_errors = {}
    st.session_state.data_loaded = False


def load_user_data() -> None:
    _load_list_result(fetch_active_memories(st.session_state.user_id), "memories", "memories")
    _load_list_result(fetch_memory_history(st.session_state.user_id), "history", "history")
    _load_list_result(fetch_conflicts(st.session_state.user_id), "conflicts", "conflicts")
    st.session_state.data_loaded = True


def load_trace_data() -> None:
    if not st.session_state.active_session_id:
        st.session_state.trace = None
        _set_error("trace", None)
        return

    trace_result = fetch_session_trace(st.session_state.active_session_id)
    _load_dict_result(trace_result, "trace", "trace")


def parse_sessions_from_input(raw_text: str) -> list[str]:
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def render_template_component(template_path: str, payload: dict, height: int) -> None:
    with open(template_path, "r", encoding="utf-8") as handle:
        html_template = handle.read()
    html_content = html_template.replace("__INJECT_JSON_HERE__", json.dumps(payload))
    components.html(html_content, height=height, scrolling=True)


def fetch_batch_traces(session_ids: list) -> None:
    for session_id in session_ids:
        if session_id in st.session_state.batch_traces:
            continue
        trace_result = fetch_session_trace(session_id)
        if trace_result.get("ok") and isinstance(trace_result.get("data"), dict):
            st.session_state.batch_traces[session_id] = trace_result["data"]
        else:
            st.session_state.last_batch_errors.append(
                {
                    "session_id": session_id,
                    "error": trace_result.get("error") or "Failed to fetch trace.",
                }
            )


_ensure_session_defaults()

user_changed = st.session_state._last_user_id != st.session_state.user_id
if user_changed or not st.session_state.data_loaded:
    load_user_data()
    st.session_state._last_user_id = st.session_state.user_id

session_changed = st.session_state._last_session_id != st.session_state.active_session_id
if st.session_state.active_session_id and (session_changed or not st.session_state.trace):
    load_trace_data()
    st.session_state._last_session_id = st.session_state.active_session_id


active_count = len(st.session_state.memories)
extracted_count = len(st.session_state.history)
conflict_count = len(st.session_state.conflicts)
sessions_set = {m.get("session_id") for m in st.session_state.history if m.get("session_id")}
session_count = len(sessions_set)

col_user, col_stats = st.columns([0.5, 3])
with col_user:
    users = ["user_001", "user_002", "user_003", "admin_user"]
    current_user_index = users.index(st.session_state.user_id) if st.session_state.user_id in users else 0
    selected_user = st.selectbox("User", users, index=current_user_index, label_visibility="collapsed")
    if selected_user != st.session_state.user_id:
        st.session_state.user_id = selected_user
        reset_user_state()
        st.rerun()

with col_stats:
    st.markdown(
        f"<div style='margin-top: 10px;'><span style='color: gray; font-size: 0.9em;'>{session_count} sessions · {extracted_count} extracted · {active_count} active · {conflict_count} conflict</span></div>",
        unsafe_allow_html=True,
    )

st.markdown("---")

if any(st.session_state.data_errors.get(key) for key in ["memories", "history", "conflicts", "trace"]):
    with st.container(border=True):
        st.warning("Data Loading Issues")
        st.caption("Some data could not be loaded from the backend. Empty states are shown where data is unavailable.")
        for key in ["memories", "history", "conflicts", "trace"]:
            error_text = st.session_state.data_errors.get(key)
            if error_text:
                st.caption(f"• {key.title()}: {error_text}")


st.subheader("New session")
st.caption("Submit a conversation to extract and consolidate memories.")
with st.form("ingestion_form"):
    session_text = st.text_area(
        "Conversation Text",
        height=100,
        label_visibility="collapsed",
        placeholder="User: Actually, I'd prefer detailed explanations going forward...\nAgent: Got it, noted.",
    )
    submit_button = st.form_submit_button("Ingest session ↗")
    if submit_button:
        if not session_text.strip():
            st.warning("Please enter some conversation text.")
        else:
            with st.spinner("Extracting and consolidating memories..."):
                result = ingest_session_result(st.session_state.user_id, session_text)
                if result.get("ok") and isinstance(result.get("data"), dict):
                    st.session_state.active_session_id = result["data"].get("session_id")
                    st.session_state.last_ingestion_result = result["data"]
                    st.session_state._last_session_id = None
                    load_user_data()
                    load_trace_data()
                    st.success(
                        "✓ Session ingested successfully! View the **Pipeline trace** tab to see execution details."
                    )
                else:
                    st.error(f"Failed to ingest session. {result.get('error') or 'Please check backend logs.'}")

st.write("")

tab_pipe, tab_graph, tab_belief, tab_lab, tab_admin = st.tabs(
    ["Pipeline trace", "Memory graph", "Current beliefs", "Threshold lab", "Admin"]
)

with tab_pipe:
    st.write("### Pipeline Trace")
    st.caption("Step-by-step execution of extraction and consolidation. Each row shows a memory extracted and its consolidation decision (ADD, UPDATE, NOOP, or CONFLICT).")

    if not st.session_state.active_session_id:
        st.info("No active session. Ingest a session to view its pipeline trace.")
    elif st.session_state.data_errors.get("trace"):
        st.error(
            f"Trace data could not be loaded for session {st.session_state.active_session_id}. {st.session_state.data_errors.get('trace')}"
        )
    elif not st.session_state.trace:
        st.info(f"No trace data available for session {st.session_state.active_session_id}.")
    else:
        render_template_component(
            "frontend/templates/trace_component.html",
            st.session_state.trace,
            height=600,
        )

with tab_graph:
    st.write("### Memory Graph")
    st.caption("Visualizes memory relationships and evolution over time. Active memories are solid; superseded ones are faded. Red outlines indicate conflicts.")

    if st.session_state.data_errors.get("history"):
        st.error(f"Memory history could not be loaded. {st.session_state.data_errors.get('history')}")
    elif not st.session_state.history:
        st.info("No memory history available. Ingest a session to build the graph.")
    else:
        render_template_component(
            "frontend/templates/graph_component.html",
            {"history": st.session_state.history, "conflicts": st.session_state.conflicts},
            height=650,
        )

with tab_belief:
    st.write("### Current Beliefs")
    st.caption("Active memories the system holds about the user, organized by type (preference, fact, event). These are injected into the agent's system prompt.")

    if st.session_state.data_errors.get("memories"):
        st.error(f"Active memories could not be loaded. {st.session_state.data_errors.get('memories')}")

    preferences = [m for m in st.session_state.memories if m.get("memory_type", "").lower() == "preference"]
    facts = [m for m in st.session_state.memories if m.get("memory_type", "").lower() == "fact"]
    events = [m for m in st.session_state.memories if m.get("memory_type", "").lower() == "event"]

    conflict_ids = set()
    for conflict in st.session_state.conflicts:
        if conflict.get("memory_id_a") and isinstance(conflict["memory_id_a"], dict):
            conflict_ids.add(conflict["memory_id_a"].get("id"))
        if conflict.get("memory_id_b") and isinstance(conflict["memory_id_b"], dict):
            conflict_ids.add(conflict["memory_id_b"].get("id"))

    if st.session_state.conflicts:
        st.error(f"{len(st.session_state.conflicts)} unresolved conflict(s)")
        st.caption("These memories contradict each other and are both kept as active. The agent sees both when making decisions.")

    def render_memory_card(memory: dict) -> None:
        mem_id = memory.get("id")
        is_conflict = mem_id in conflict_ids

        with st.container(border=True):
            st.write(memory.get("content", ""))
            confidence = memory.get("confidence", 0.0)
            session_id = memory.get("session_id", "Unknown")
            if is_conflict:
                st.caption(f"Confidence: {confidence} | Session: {session_id} | **Conflicted**")
            else:
                st.caption(f"Confidence: {confidence} | Session: {session_id}")

    col_pref, col_fact, col_evt = st.columns(3)

    with col_pref:
        st.markdown("##### PREFERENCES")
        if not preferences:
            st.caption("No preferences recorded")
        for memory in preferences:
            render_memory_card(memory)

    with col_fact:
        st.markdown("##### FACTS")
        if not facts:
            st.caption("No facts recorded")
        for memory in facts:
            render_memory_card(memory)

    with col_evt:
        st.markdown("##### EVENTS")
        if not events:
            st.caption("No events recorded")
        for memory in events:
            render_memory_card(memory)

    if st.session_state.conflicts:
        st.write("---")
        st.subheader("Conflicts")
        st.caption("These memory pairs contradict each other. Both remain active unless one is removed or clarified.")
        for conflict in st.session_state.conflicts:
            mem_a = conflict.get("memory_id_a", {})
            mem_b = conflict.get("memory_id_b", {})
            content_a = mem_a.get("content", "Unknown") if isinstance(mem_a, dict) else str(mem_a)
            content_b = mem_b.get("content", "Unknown") if isinstance(mem_b, dict) else str(mem_b)
            st.error(
                f"**{content_a[:40]}...**  vs  **{content_b[:40]}...**\n\nBoth memories are active. Consider clarifying whether these conditions are mutually exclusive or if one is outdated."
            )

with tab_lab:
    st.write("### Threshold Lab")
    st.caption("Explores tradeoffs in the similarity threshold (θ) used by the consolidation pipeline. Lower θ merges more aggressively; higher θ preserves more memories.")

    col_run, _ = st.columns([1, 4])
    with col_run:
        if st.button("Re-run sweep"):
            with st.spinner("Running threshold sweep..."):
                results = fetch_threshold_sweep()
                if results.get("ok") and isinstance(results.get("data"), dict) and "results" in results["data"]:
                    st.session_state.sweep_results = results["data"]["results"]
                    st.success("Sweep complete!")
                else:
                    st.session_state.sweep_results = None
                    st.error(f"Failed to fetch sweep results. {results.get('error') or ''}")

    if st.session_state.sweep_results:
        df = pd.DataFrame(st.session_state.sweep_results)
        if df.empty or "threshold" not in df.columns:
            st.info("Sweep returned no usable results.")
        else:
            available_thresholds = sorted(df["threshold"].unique().tolist())
            st.write("#### Tradeoff Analysis")
            st.caption("θ (theta) is the cosine similarity threshold. When two memories exceed θ similarity, the LLM decides if they should be merged (UPDATE), ignored (NOOP), or marked as conflicting.")
            selected_threshold = st.select_slider(
                "θ threshold",
                options=available_thresholds,
                value=available_thresholds[len(available_thresholds) // 2] if available_thresholds else None,
            )

            if selected_threshold is not None:
                filtered = df[df["threshold"] == selected_threshold]
                if filtered.empty:
                    st.info("No sweep row matched the selected threshold.")
                else:
                    current_data = filtered.iloc[0]
                    col_kpis1, col_kpis2, col_kpis3, col_kpis4 = st.columns(4)
                    col_kpis1.metric("Selected \u03b8", f"{selected_threshold:.2f}")
                    col_kpis2.metric("False Merges", int(current_data["false_merges"]), help="Memories incorrectly merged despite being distinct.")
                    col_kpis3.metric("Missed Conflicts", int(current_data["missed_conflicts"]), help="Contradictory memories not detected as conflicts.")
                    col_kpis4.metric("LLM Calls", int(current_data["total_llm_calls"]), help="Number of LLM-based consolidation decisions made.")

                    st.write("#### False Merges vs Missed Conflicts")
                    chart_data = df.set_index("threshold")[["false_merges", "missed_conflicts"]]
                    st.line_chart(chart_data)
    else:
        st.info("Click 'Re-run sweep' to evaluate consolidation thresholds on the ground truth dataset.")

with tab_admin:
    st.write("### Admin Mode")
    st.caption("Advanced features: batch ingestion (multiple sessions at once) and combined trace analysis across multiple sessions.")

    st.write("#### Batch Ingestion")
    st.caption("Paste multiple conversations, separated by blank lines. Each non-empty line is treated as a separate session.")
    batch_text = st.text_area(
        "Multiple Sessions",
        height=150,
        placeholder="Session 1 text here...\nSession 2 text here...\nSession 3 text here...",
    )

    parsed_sessions = parse_sessions_from_input(batch_text)

    if parsed_sessions:
        st.info(f"{len(parsed_sessions)} session(s) parsed and ready to ingest.")
        with st.expander("Preview Parsed Sessions", expanded=False):
            for index, session in enumerate(parsed_sessions):
                preview = session[:80] + "..." if len(session) > 80 else session
                st.caption(f"**Session {index + 1}**: {preview}")

        if st.button("Ingest All Sessions", key="batch_ingest_button"):
            st.session_state.batch_sessions = parsed_sessions
            st.session_state.batch_traces = {}
            st.session_state.last_batch_errors = []

            progress_placeholder = st.empty()
            status_text = st.empty()
            progress_value = 0

            result_stats = {
                "total": len(parsed_sessions),
                "successful": 0,
                "failed": 0,
                "session_ids": [],
            }

            for index, session_text in enumerate(parsed_sessions):
                status_text.text(f"Ingesting session {index + 1} of {len(parsed_sessions)}...")
                result = ingest_session_result(st.session_state.user_id, session_text)
                if result.get("ok") and isinstance(result.get("data"), dict) and result["data"].get("session_id"):
                    result_stats["successful"] += 1
                    result_stats["session_ids"].append(result["data"].get("session_id"))
                else:
                    result_stats["failed"] += 1
                    st.session_state.last_batch_errors.append(
                        {
                            "session_index": index,
                            "error": result.get("error") or "API response empty or missing session_id",
                        }
                    )

                progress_value = (index + 1) / len(parsed_sessions)
                progress_placeholder.progress(progress_value)

            st.session_state.last_batch_result = result_stats
            st.session_state.batch_traces = {}
            status_text.text(f"Ingestion complete: {result_stats['successful']} successful, {result_stats['failed']} failed.")
            if result_stats["failed"] == 0:
                st.success("All sessions ingested successfully!")
            load_user_data()
            st.rerun()

    if st.session_state.last_batch_result:
        st.write("#### Combined Trace Results")
        st.caption("Aggregated traces from all ingested sessions in this batch.")
        batch_ids = st.session_state.last_batch_result.get("session_ids", [])

        fetch_batch_traces(batch_ids)

        total_steps = 0
        decisions = {}
        for session_id in batch_ids:
            trace = st.session_state.batch_traces.get(session_id, {})
            steps = trace.get("steps", [])
            total_steps += len(steps)
            for step in steps:
                decision = step.get("decision", "UNKNOWN")
                decisions[decision] = decisions.get(decision, 0) + 1

        if decisions:
            decision_summary = ", ".join(f"{decision}: {count}" for decision, count in decisions.items())
        else:
            decision_summary = "No decisions recorded"
        st.metric("Total Pipeline Steps", total_steps)
        st.caption(f"Decision distribution: {decision_summary}")

        if st.session_state.last_batch_errors:
            with st.expander("Batch errors", expanded=False):
                for error in st.session_state.last_batch_errors:
                    st.caption(f"Session {error['session_index'] + 1}: {error['error']}")

        for index, session_id in enumerate(batch_ids):
            trace_data = st.session_state.batch_traces.get(session_id)
            if not trace_data:
                continue
            with st.expander(f"Session {index + 1}: {session_id} ({trace_data.get('duration_ms', 0)}ms)", expanded=False):
                render_template_component("frontend/templates/trace_component.html", trace_data, height=400)
