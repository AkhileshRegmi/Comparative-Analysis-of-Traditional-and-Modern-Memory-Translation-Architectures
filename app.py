"""Paging simulator: entry point with the page navigation. Run with `streamlit run app.py`."""
import streamlit as st

st.set_page_config(page_title="Paging simulator", layout="wide")
st.navigation([
    st.Page("views/simulator.py", title="Simulator", icon=":material/memory:", default=True),
    st.Page("views/analysis.py", title="Analysis", icon=":material/insights:"),
    st.Page("views/about.py", title="About us", icon=":material/groups:"),
]).run()
