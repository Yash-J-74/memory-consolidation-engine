import streamlit as st
import time
from api_client import (
    ingest_session, 
    get_active_memories, 
    get_memory_history, 
    get_conflicts, 
    get_session_trace
)

st.set_page_config(page_title="Memory Consolidation Engine", layout="wide")

# Initialize session state variables
if "user_id" not in st.session_state:
    st.session_state.user_id = "user_001"
if "active_session_id" not in st.session_state:
    st.session_state.active_session_id = None
if "last_ingestion_result" not in st.session_state:
    st.session_state.last_ingestion_result = None

# Initialize data state
if "memories" not in st.session_state: st.session_state.memories = []
if "history" not in st.session_state: st.session_state.history = []
if "conflicts" not in st.session_state: st.session_state.conflicts = []
if "trace" not in st.session_state: st.session_state.trace = None
if "data_loaded" not in st.session_state: st.session_state.data_loaded = False

def load_user_data():
    st.session_state.memories = get_active_memories(st.session_state.user_id)
    st.session_state.history = get_memory_history(st.session_state.user_id)
    st.session_state.conflicts = get_conflicts(st.session_state.user_id)
    st.session_state.data_loaded = True

def load_trace_data():
    if st.session_state.active_session_id:
        st.session_state.trace = get_session_trace(st.session_state.active_session_id)

# Perform initial data fetch
if not st.session_state.data_loaded:
    load_user_data()

# Fetch trace if we have an active session but no trace loaded yet, 
# or if the loaded trace doesn't match the current active session
if st.session_state.active_session_id:
    if not st.session_state.trace or st.session_state.trace.get("session_id") != st.session_state.active_session_id:
        load_trace_data()

# --- HEADER BLOCK ---
active_count = len(st.session_state.memories)
extracted_count = len(st.session_state.history)
conflict_count = len(st.session_state.conflicts)
# Count unique session IDs by deduping properties in memory history
sessions_set = set(m.get("session_id") for m in st.session_state.history if m.get("session_id"))
session_count = len(sessions_set)

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f"**{st.session_state.user_id}** | "
                f"<span style='color: gray; font-size: 0.9em;'>{session_count} sessions · {extracted_count} extracted · {active_count} active · {conflict_count} conflict</span>", 
                unsafe_allow_html=True)
with col2:
    st.markdown("<div style='text-align: right; color: gray; font-size: 0.8em;'>last ingested --</div>", unsafe_allow_html=True)

st.markdown("---")

# --- INGESTION BLOCK ---
st.subheader("New session")
with st.form("ingestion_form"):
    session_text = st.text_area("Conversation Text", height=100, label_visibility="collapsed",
                                placeholder="User: Actually, I'd prefer detailed explanations going forward...\nAgent: Got it, noted.")
    submit_button = st.form_submit_button("Ingest session ↗")
    if submit_button:
        if not session_text.strip():
            st.warning("Please enter some conversation text.")
        else:
            with st.spinner("Extracting and consolidating memories..."):
                result = ingest_session(st.session_state.user_id, session_text)
                if result:
                    st.session_state.active_session_id = result.get("session_id")
                    st.session_state.last_ingestion_result = result
                    load_user_data()
                    load_trace_data()
                    st.success("Session ingested successfully! Please view the **Pipeline trace** tab below to view the execution results.")
                else:
                    st.error("Failed to ingest session. Please check backend logs.")

st.write("") # spacing

# --- VISUALIZATION BLOCK (TABS) ---
tab_pipe, tab_graph, tab_belief, tab_lab, tab_admin = st.tabs([
    "Pipeline trace", 
    "Memory graph", 
    "Current beliefs", 
    "Threshold lab", 
    "Admin"
])

import json
import streamlit.components.v1 as components

with tab_pipe:
    st.write("### Pipeline Trace")
    st.write("Displays step-by-step execution of extraction and consolidation for a session.")
    
    if not st.session_state.active_session_id:
        st.info("No active session. Ingest a session to view its pipeline trace.")
    elif not st.session_state.trace:
        st.warning(f"No trace data found for session {st.session_state.active_session_id}.")
    else:
        # Load the HTML template
        with open("frontend/templates/trace_component.html", "r", encoding="utf-8") as f:
            html_template = f.read()
            
        # Serialize the trace dict to JSON
        trace_json = json.dumps(st.session_state.trace)
        
        # Inject the JSON into the template
        html_content = html_template.replace("__INJECT_JSON_HERE__", trace_json)
        
        # Render the custom component.
        # Height is fixed initially, scrolling is set to true.
        components.html(html_content, height=600, scrolling=True)

with tab_graph:
    st.write("### Memory Graph")
    st.write("Visualizes memory relationships and evolution.")
    
    if not st.session_state.history:
        st.info("No memory history available. Ingest a session to build the graph.")
    else:
        # Load the HTML template
        with open("frontend/templates/graph_component.html", "r", encoding="utf-8") as f:
            html_template = f.read()
            
        # Serialize the combined data
        graph_data = {
            "history": st.session_state.history,
            "conflicts": st.session_state.conflicts
        }
        graph_json = json.dumps(graph_data)
        
        # Inject the JSON into the template
        html_content = html_template.replace("__INJECT_JSON_HERE__", graph_json)
        
        # Render the custom component.
        components.html(html_content, height=650, scrolling=True)

with tab_belief:
    st.write("### Current Beliefs")
    st.caption("What the agent injects into its system prompt.")

    # 1. Process data
    preferences = [m for m in st.session_state.memories if m.get("memory_type", "").lower() == "preference"]
    facts = [m for m in st.session_state.memories if m.get("memory_type", "").lower() == "fact"]
    events = [m for m in st.session_state.memories if m.get("memory_type", "").lower() == "event"]

    # Extract conflicting IDs
    conflict_ids = set()
    for c in st.session_state.conflicts:
        if c.get("memory_id_a") and isinstance(c["memory_id_a"], dict):
            conflict_ids.add(c["memory_id_a"].get("id"))
        if c.get("memory_id_b") and isinstance(c["memory_id_b"], dict):
            conflict_ids.add(c["memory_id_b"].get("id"))

    # 2. Render UI
    if st.session_state.conflicts:
        st.error(f"{len(st.session_state.conflicts)} conflict(s) require resolution.")

    st.write("")

    def render_memory_card(memory):
        mem_id = memory.get("id")
        is_conflict = mem_id in conflict_ids
        
        with st.container(border=True):
            st.write(memory.get("content", ""))
            conf = memory.get('confidence', 0.0)
            session = memory.get('session_id', 'Unknown')
            
            if is_conflict:
                st.caption(f"Confidence: {conf} | Session: {session} | ⚠️ **Conflict**")
            else:
                st.caption(f"Confidence: {conf} | Session: {session}")

    col_pref, col_fact, col_evt = st.columns(3)

    with col_pref:
        st.markdown("##### 🛠️ PREFERENCES")
        if not preferences:
            st.caption("No preferences recorded")
        for m in preferences:
            render_memory_card(m)

    with col_fact:
        st.markdown("##### 📊 FACTS")
        if not facts:
            st.caption("No facts recorded")
        for m in facts:
            render_memory_card(m)

    with col_evt:
        st.markdown("##### 🕰️ EVENTS")
        if not events:
            st.caption("No events recorded")
        for m in events:
            render_memory_card(m)

    # 3. Conflict Callout Section
    if st.session_state.conflicts:
        st.write("---")
        for c in st.session_state.conflicts:
            mem_a = c.get("memory_id_a", {})
            mem_b = c.get("memory_id_b", {})
            content_a = mem_a.get("content", "Unknown") if isinstance(mem_a, dict) else str(mem_a)
            content_b = mem_b.get("content", "Unknown") if isinstance(mem_b, dict) else str(mem_b)
            
            msg = f"**Unresolved conflict — {content_a[:30]}...**\n\n\"{content_a}\" vs \"{content_b}\" — classified as CONFLICT. Both are active. Resolve by clarifying whether the conditions are mutually exclusive."
            st.error(msg, icon="⚠️")

with tab_lab:
    st.write("### Threshold Lab")
    st.write("Explores tradeoffs in consolidation threshold.")

with tab_admin:
    st.write("### Admin Mode")
    st.write("Multi-session ingestion and user switching.")
