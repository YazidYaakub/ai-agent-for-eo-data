"""
GeoVision AI - Intelligent Satellite Imagery Analysis Platform

A conversational AI application for searching, downloading, and analyzing
Planet satellite imagery through natural language interactions.
"""

import streamlit as st
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import agent modules
from agents import Runner, trace
from geovision_agents import (
    unified_agent,
    create_session
)

# Page configuration
st.set_page_config(
    page_title="GeoVision AI",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session" not in st.session_state:
    st.session_state.session = create_session()
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = {}
if "search_results" not in st.session_state:
    st.session_state.search_results = None
if "downloaded_files" not in st.session_state:
    st.session_state.downloaded_files = []


def save_uploaded_file(uploaded_file) -> Path:
    """Save uploaded file to temporary directory."""
    upload_dir = Path("uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    logger.info(f"Saved uploaded file: {file_path}")
    return file_path


def display_sidebar():
    """Display sidebar with file upload and system information."""
    with st.sidebar:
        # File upload section
        st.subheader("📁 Upload Files")
        
        # GeoJSON upload
        geojson_file = st.file_uploader(
            "Area of Interest (GeoJSON)",
            type=["geojson", "json"],
            key="geojson_uploader"
        )
        
        if geojson_file:
            file_path = save_uploaded_file(geojson_file)
            st.session_state.uploaded_files["aoi"] = str(file_path)
            st.success(f"✓ Loaded: {geojson_file.name}")
        
        # Image upload
        image_file = st.file_uploader(
            "Satellite Image (TIFF)",
            type=["tif", "tiff"],
            key="image_uploader"
        )
        
        if image_file:
            file_path = save_uploaded_file(image_file)
            st.session_state.uploaded_files["image"] = str(file_path)
            st.success(f"✓ Loaded: {image_file.name}")

        # System status
        st.subheader("🔧 System Status")
        
        planet_key = os.getenv("PL_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        
        st.markdown(f"**Planet API:** {'✓ Connected' if planet_key else '✗ Missing'}")
        st.markdown(f"**OpenAI API:** {'✓ Connected' if openai_key else '✗ Missing'}")
        
        if st.session_state.uploaded_files:
            st.markdown("**Uploaded Files:**")
            for file_type, path in st.session_state.uploaded_files.items():
                st.markdown(f"- {file_type}: `{Path(path).name}`")

        # Clear conversation
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.search_results = None
            st.rerun()


def extract_image_paths(content: str) -> list:
    """Extract image file paths from content."""
    import re

    # Pattern 1: Absolute paths starting with / (handles spaces in path)
    # Pattern 2: Relative paths like outputs/file.png or downloads/file.tif
    pattern1 = r'(/[^\n<>]+?\.(?:png|jpg|jpeg|tiff|tif))\b'
    pattern2 = r'\b((?:outputs|downloads|uploads)/[^\s<>]+?\.(?:png|jpg|jpeg|tiff|tif))\b'

    matches = []
    matches.extend(re.findall(pattern1, content, re.IGNORECASE))
    matches.extend(re.findall(pattern2, content, re.IGNORECASE))

    # Resolve all paths to absolute and deduplicate by resolved path
    seen_resolved = set()
    valid_paths = []

    for path in matches:
        # Resolve to absolute path
        if Path(path).is_absolute():
            resolved = Path(path).resolve()
        else:
            resolved = (Path.cwd() / path).resolve()

        # Check if file exists and hasn't been seen
        if resolved.exists() and str(resolved) not in seen_resolved:
            seen_resolved.add(str(resolved))
            valid_paths.append(str(resolved))
            logger.info(f"Found valid image path: {resolved}")

    return valid_paths


def display_chat_message(role: str, content: str):
    """Display a chat message with appropriate styling and embedded images."""
    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
    else:
        with st.chat_message("assistant", avatar="🛰️"):
            # Display text content
            st.markdown(content)

            # Check for and display any images referenced in the content
            image_paths = extract_image_paths(content)
            if image_paths:
                for img_path in image_paths:
                    try:
                        # Only display PNG/JPG images, not raw TIFFs (which need rasterio)
                        if img_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                            # Use fixed width of 600px for reasonable display size
                            st.image(img_path, caption=Path(img_path).name, width=600)
                            logger.info(f"Displayed image: {img_path}")
                    except Exception as e:
                        logger.error(f"Error displaying image {img_path}: {e}")
                        st.error(f"Could not display image: {Path(img_path).name}")


async def process_user_input(user_input: str):
    """Process user input through the agent system."""
    try:
        # Enhance input with uploaded files context if available
        enhanced_input = user_input
        if st.session_state.uploaded_files:
            # Pass full paths, not just filenames
            files_info = ", ".join([f"{k}: {v}" for k, v in st.session_state.uploaded_files.items()])
            enhanced_input = f"[SYSTEM CONTEXT - User has uploaded files with these paths: {files_info}. Use these exact paths when calling tools.]\n\nUser request: {user_input}"

        # Run through agent system
        # Session memory automatically handles conversation history
        with trace(workflow_name="GeoVision AI Chat"):
            result = await Runner.run(
                unified_agent,
                input=enhanced_input,  # Pass string input, not list
                session=st.session_state.session
            )

        return result.final_output

    except Exception as e:
        logger.error(f"Error processing input: {e}", exc_info=True)
        return f"I encountered an error: {str(e)}. Please try again."


def main():
    """Main application entry point."""
    # Display sidebar
    display_sidebar()

    # Display chat history
    for message in st.session_state.messages:
        display_chat_message(message["role"], message["content"])
    
    # Chat input
    if prompt := st.chat_input("What would you like to do with satellite imagery today?"):
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": prompt})
        display_chat_message("user", prompt)
        
        # Process and get response
        with st.chat_message("assistant", avatar="🛰️"):
            with st.spinner("Thinking..."):
                import asyncio
                response = asyncio.run(process_user_input(prompt))
                st.markdown(response)

                # Display any images referenced in the response
                image_paths = extract_image_paths(response)
                if image_paths:
                    for img_path in image_paths:
                        try:
                            # Only display PNG/JPG images, not raw TIFFs (which need rasterio)
                            if img_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                                # Use fixed width of 600px for reasonable display size
                                st.image(img_path, caption=Path(img_path).name, width=600)
                                logger.info(f"Displayed image: {img_path}")
                        except Exception as e:
                            logger.error(f"Error displaying image {img_path}: {e}")
                            st.error(f"Could not display image: {Path(img_path).name}")
        
        # Add assistant response to history
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()


if __name__ == "__main__":
    main()
