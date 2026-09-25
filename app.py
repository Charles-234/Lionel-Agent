"""Lionel web interface with file upload support.

This file is a thin outside door, the same idea as telegram_door.py. It
never plans, never picks a role, never authorizes, never runs tools, and
never audits. It only:

1. Shows a chat page in the browser.
2. Accepts text and file uploads.
3. Passes them into agent.chat.chat().
4. Shows the reply.

The governance chain stays where it is. Streamlit is just a new door.
"""

from __future__ import annotations

import logging
import uuid

import streamlit as st

from agent.chat import chat
from agent.safety import sanitize_for_display

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Lionel", page_icon="🦁", layout="centered")
st.title("Lionel")

# --- Session identity ---
if "lionel_user_id" not in st.session_state:
    st.session_state.lionel_user_id = abs(hash(uuid.uuid4().hex)) % (10**9)

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Sidebar: file uploader ---
with st.sidebar:
    st.header("Attach a file")
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=None,
        accept_multiple_files=False,
    )
    st.caption("Documents, images, audio, or video are accepted.")

# --- Draw existing chat ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Handle new input ---
prompt = st.chat_input("Ask Lionel something...")

if prompt or uploaded_file:
    user_text = prompt or ""
    if uploaded_file and not user_text:
        user_text = "Please analyze this file and tell me what you see."

    # Show the user's message.
    display_text = user_text
    if uploaded_file:
        display_text = f"[File: {uploaded_file.name}] {user_text}"
    st.session_state.messages.append({"role": "user", "content": display_text})
    with st.chat_message("user"):
        st.markdown(display_text)

    # Prepare the file bytes.
    file_bytes = None
    mime_type = "application/octet-stream"
    file_name = "attachment"

    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        mime_type = uploaded_file.type or "application/octet-stream"
        file_name = uploaded_file.name

    # Call the core.
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                if mime_type.startswith("image/"):
                    response = chat(
                        user_id=st.session_state.lionel_user_id,
                        user_message=user_text,
                        include_skills=True,
                        image_bytes=file_bytes,
                        image_mime_type=mime_type,
                    )
                elif file_bytes is not None:
                    response = chat(
                        user_id=st.session_state.lionel_user_id,
                        user_message=user_text,
                        include_skills=True,
                        attachment_bytes=file_bytes,
                        attachment_mime_type=mime_type,
                        attachment_name=file_name,
                    )
                else:
                    response = chat(
                        user_id=st.session_state.lionel_user_id,
                        user_message=user_text,
                        include_skills=True,
                    )

                reply_text = sanitize_for_display(response.text) if response.text else "(no reply)"

                if response.error:
                    logger.warning("Chat returned error flag: %s", response.error)

            except Exception:
                logger.exception("Chat call failed")
                reply_text = "I could not handle that. Please try again."

        st.markdown(reply_text)

    st.session_state.messages.append(
        {"role": "assistant", "content": reply_text}
    )