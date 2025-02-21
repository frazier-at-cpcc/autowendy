import subprocess
import streamlit as st
from app import main

# Install playwright browser on startup
try:
    subprocess.run(["playwright", "install", "chromium"], check=True)
except Exception as e:
    st.error(f"Failed to install browser: {e}")

# Run the main app
main()
