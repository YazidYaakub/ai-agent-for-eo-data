"""
Queryable Earth - Natural Language Interface for Planet Satellite Imagery
Main Streamlit Application
"""
import streamlit as st
import os
import sys
import json
from datetime import datetime

# Add tools and agents to path
sys.path.insert(0, os.path.dirname(__file__))

from agents.orchestrator import AgentOrchestrator
from tools.planet_connector import PlanetConnector
from tools.ndvi_calculator import NDVICalculator
from tools.change_detector import ChangeDetector
from tools.semantic_search import SemanticSearch

# Page configuration
st.set_page_config(
    page_title="GeoQuery AI - Satellite Imagery Analysis",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #2E86AB;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
        background-color: #2E86AB;
        color: white;
        font-weight: bold;
        padding: 0.75rem;
        border-radius: 0.5rem;
    }
    .sample-query {
        background-color: #f0f2f6;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        margin: 0.25rem 0;
        cursor: pointer;
        transition: background-color 0.3s;
    }
    .sample-query:hover {
        background-color: #e0e2e6;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'orchestrator' not in st.session_state:
    st.session_state.orchestrator = None
if 'query_history' not in st.session_state:
    st.session_state.query_history = []
if 'current_result' not in st.session_state:
    st.session_state.current_result = None
if 'chat_messages' not in st.session_state:
    st.session_state.chat_messages = []
if 'messages_for_api' not in st.session_state:
    # Messages in OpenAI API format for maintaining context
    st.session_state.messages_for_api = [{
        "role": "system",
        "content": """You are an AI agent that helps users analyze satellite imagery from Planet Labs.

You have access to the following tools:
1. search_satellite_imagery - Search for imagery in specific locations or coordinates
2. calculate_ndvi - Analyze vegetation health (downloads real satellite imagery - takes 30-60 seconds)
3. detect_changes - Find changes between two time periods
4. semantic_search_imagery - Search using natural language descriptions

CRITICAL RULES FOR ITEM IDS:
- ONLY use item IDs that were returned from search_satellite_imagery results
- NEVER invent or construct item IDs
- When calling calculate_ndvi or detect_changes, ALWAYS use exact item IDs from previous search results
- If you don't have search results yet, run search_satellite_imagery FIRST
- Item IDs look like: "20251224_041209_06_251b" (date_time_sensor_id format)

IMPORTANT NOTES:
- calculate_ndvi downloads ~100-500MB of satellite imagery - inform users this takes time
- Always tell users which item IDs you're analyzing
- If an item ID returns 404 error, it means that ID doesn't exist - use a different one from search results

When a user asks a question:
1. Search for imagery FIRST if you don't have item IDs
2. Use ONLY the item IDs returned from search
3. Call the appropriate analysis tools with those exact IDs
4. Synthesize the results into a clear, actionable answer
5. Include specific data and insights from the analysis

Be professional, data-driven, and provide actionable insights. When users ask follow-up questions, remember the context from previous messages."""
    }]


def initialize_orchestrator():
    """Initialize the AI agent orchestrator"""
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        planet_key = os.getenv("PLANET_API_KEY")
        
        if not openai_key or not planet_key:
            return False, "API keys not found. Please set OPENAI_API_KEY and PLANET_API_KEY in .env file"
        
        st.session_state.orchestrator = AgentOrchestrator(
            openai_api_key=openai_key,
            planet_api_key=planet_key
        )
        return True, "Orchestrator initialized successfully"
    except Exception as e:
        return False, f"Error initializing: {str(e)}"


def main():
    # Header
    st.markdown('<div class="main-header">🛰️ GeoQuery AI</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Natural Language Interface for Satellite Imagery Analysis</div>',
        unsafe_allow_html=True
    )
    
    # Sidebar
    with st.sidebar:
        # API Status
        st.subheader("🔑 API Status")

        openai_status = "✅" if os.getenv("OPENAI_API_KEY") else "❌"
        planet_status = "✅" if os.getenv("PLANET_API_KEY") else "❌"

        st.write(f"{openai_status} OpenAI API")
        st.write(f"{planet_status} Planet API")

        st.markdown("---")

        # About
        st.header("📋 About")
        st.write("""
        **GeoQuery AI** - An AI-powered natural language interface for satellite imagery analysis.

        **Current Features:**
        - 🔍 Natural language queries
        - 🌱 NDVI vegetation analysis
        - 💬 Conversational memory

        **Future Improvements:**
        - 🔄 Change detection
        - 🗺️ Semantic imagery search
        - 🤖 Multi-agent orchestration
        - 🛰️ Real satellite data integration
        """)

        st.markdown("---")

        # Query History
        if st.session_state.query_history:
            st.header("📜 Recent Queries")
            for i, query in enumerate(reversed(st.session_state.query_history[-5:]), 1):
                st.write(f"{i}. {query[:50]}...")
    
    # Main content area - Chat Interface
    st.header("💬 Satellite Imagery Analysis Chat")

    # Sample queries in expandable section
    with st.expander("📝 Click to see sample queries"):
        sample_col1, sample_col2 = st.columns(2)

        sample_queries = [
            "Show me padi fields in Sekinchan, Malaysia"
        ]

        for i, query in enumerate(sample_queries):
            col = sample_col1 if i % 2 == 0 else sample_col2
            with col:
                if st.button(query, key=f"sample_{query}", use_container_width=True):
                    # Add to chat input
                    st.session_state.pending_query = query
                    st.rerun()

    # Display chat history
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

                # Display visualizations if present
                if "visualizations" in msg and msg["visualizations"]:
                    for viz in msg["visualizations"]:
                        st.image(viz, use_container_width=True)

    # Clear conversation button
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🗑️ Clear Chat"):
            # Completely reset conversation memory
            st.session_state.chat_messages = []
            st.session_state.current_result = None
            st.session_state.query_history = []

            # Reset API messages with fresh system prompt
            st.session_state.messages_for_api = [{
                "role": "system",
                "content": """You are an AI agent that helps users analyze satellite imagery from Planet Labs.

You have access to the following tools:
1. search_satellite_imagery - Search for imagery in specific locations or coordinates
2. calculate_ndvi - Analyze vegetation health (downloads real satellite imagery - takes 30-60 seconds)
3. detect_changes - Find changes between two time periods
4. semantic_search_imagery - Search using natural language descriptions

CRITICAL RULES FOR ITEM IDS:
- ONLY use item IDs that were returned from search_satellite_imagery results
- NEVER invent or construct item IDs
- When calling calculate_ndvi or detect_changes, ALWAYS use exact item IDs from previous search results
- If you don't have search results yet, run search_satellite_imagery FIRST
- Item IDs look like: "20251224_041209_06_251b" (date_time_sensor_id format)

IMPORTANT NOTES:
- calculate_ndvi downloads ~100-500MB of satellite imagery - inform users this takes time
- Always tell users which item IDs you're analyzing
- If an item ID returns 404 error, it means that ID doesn't exist - use a different one from search results

When a user asks a question:
1. Search for imagery FIRST if you don't have item IDs
2. Use ONLY the item IDs returned from search
3. Call the appropriate analysis tools with those exact IDs
4. Synthesize the results into a clear, actionable answer
5. Include specific data and insights from the analysis

Be professional, data-driven, and provide actionable insights. When users ask follow-up questions, remember the context from previous messages."""
            }]

            st.rerun()

    # Chat input at the bottom
    user_input = st.chat_input("Ask about satellite imagery...")

    # Handle pending query from sample buttons
    if hasattr(st.session_state, 'pending_query'):
        user_input = st.session_state.pending_query
        delattr(st.session_state, 'pending_query')

    # Process user input
    if user_input:
        if not st.session_state.orchestrator:
            with st.spinner("Initializing system..."):
                success, message = initialize_orchestrator()
                if not success:
                    st.error(message)
                    st.stop()

        # Add user message to chat
        st.session_state.chat_messages.append({
            "role": "user",
            "content": user_input
        })

        # Display user message immediately
        with st.chat_message("user"):
            st.write(user_input)

        # Process query with conversation context
        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                result = st.session_state.orchestrator.process_query(
                    user_input,
                    messages=st.session_state.messages_for_api.copy()
                )

                if result.get("success"):
                    response_text = result["response"]
                    st.write(response_text)

                    # Extract visualizations from conversation history
                    visualizations = []
                    if result.get("conversation_history"):
                        for response_obj in result.get("conversation_history", []):
                            # Try to extract from response object's output
                            if hasattr(response_obj, 'output') and isinstance(response_obj.output, list):
                                for output_item in response_obj.output:
                                    # Check if this is text output that might contain tool results
                                    if hasattr(output_item, 'text'):
                                        text = output_item.text
                                        if "visualization" in text:
                                            import re
                                            # Extract base64 images from JSON in the text
                                            pattern = r'"visualization":\s*"(data:image/png;base64,[A-Za-z0-9+/=]+)"'
                                            matches = re.findall(pattern, text)
                                            for match in matches:
                                                if match not in visualizations:
                                                    visualizations.append(match)
                                                    st.image(match, caption="NDVI Analysis", use_container_width=True)

                    # Also check in the messages (where tool results are stored)
                    if result.get("messages"):
                        for msg in result["messages"]:
                            if msg.get("role") == "user" and "Tool" in msg.get("content", ""):
                                content = msg.get("content", "")
                                if "visualization" in content:
                                    import re
                                    import json
                                    try:
                                        # Try to extract JSON from the content
                                        json_match = re.search(r'\{.*"visualization".*\}', content, re.DOTALL)
                                        if json_match:
                                            tool_result = json.loads(json_match.group())
                                            if "visualization" in tool_result:
                                                viz = tool_result["visualization"]
                                                if viz and viz not in visualizations:
                                                    visualizations.append(viz)
                                                    st.image(viz, caption="NDVI Analysis", use_container_width=True)
                                    except:
                                        # Fallback to regex extraction
                                        pattern = r'"visualization":\s*"(data:image/png;base64,[A-Za-z0-9+/=]+)"'
                                        matches = re.findall(pattern, content)
                                        for match in matches:
                                            if match not in visualizations:
                                                visualizations.append(match)
                                                st.image(match, caption="NDVI Analysis", use_container_width=True)

                    # Final fallback: search in string representation
                    if not visualizations and result.get("conversation_history"):
                        for msg in result.get("conversation_history", []):
                            msg_str = str(msg)
                            if "visualization" in msg_str and "data:image/png;base64" in msg_str:
                                import re
                                # More robust pattern that handles long base64 strings
                                pattern = r'"visualization":\s*"(data:image/png;base64,[A-Za-z0-9+/=]+)"'
                                matches = re.findall(pattern, msg_str)
                                for match in matches:
                                    if match not in visualizations:
                                        visualizations.append(match)
                                        st.image(match, caption="NDVI Analysis", use_container_width=True)

                    # Add assistant message to chat history
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": response_text,
                        "visualizations": visualizations
                    })

                    # Update API messages for next turn
                    if "messages" in result:
                        st.session_state.messages_for_api = result["messages"]

                else:
                    error_msg = result.get("response", "Unknown error occurred")
                    st.error(error_msg)
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": f"Error: {error_msg}"
                    })

        st.rerun()


if __name__ == "__main__":
    # Check for API keys on startup
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("PLANET_API_KEY"):
        st.warning("⚠️ API keys not configured. Please create a .env file with your API keys.")
        st.code("""
# Create a .env file with:
OPENAI_API_KEY=your_openai_key_here
PLANET_API_KEY=your_planet_key_here
        """)
    
    main()
