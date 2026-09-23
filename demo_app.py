"""Public hosting entrypoint: no credentials, uploads, or shared project database."""
from pathlib import Path
import runpy
import streamlit as st

st.session_state['_public_demo'] = True
runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
