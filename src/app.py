import streamlit as st
from graphstats2 import draw_graphs, parse_log_lines


if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = None


st.title("Klippy Log Analyzer")
st.subheader("Welcome to the fork of graphstats.py")
st.markdown(
    "The original `graphstats.py` is located at [here](https://github.com/Klipper3d/klipper/blob/master/scripts/graphstats.py)"
)
st.markdown(
    "This fork adds the viewing of the plots right here, with no need to install python"
)
st.sidebar.header("File Upload")
st.session_state.uploaded_file = st.sidebar.file_uploader(
    ":page_facing_up: Upload your klippy.log", type="log"
)

# progress_text = "Operation in progress. Please wait."
# my_bar = st.progress(0, text=progress_text)

if "uploaded_file" in st.session_state and st.session_state.uploaded_file is not None:

    with st.session_state.uploaded_file as file:
        content = file.getvalue()
        text = content.decode("utf-8")
        # st.write(text)
        log_data = parse_log_lines(text.splitlines())
        figures = draw_graphs(log_data)

        tab1, tab2, tab3, tab4 = st.tabs([name for name, _ in figures])

        for idx, (name, figure) in enumerate(figures):
            tab = globals()["tab" + str(idx + 1)]
            tab.title(name)
            tab.write(figure)
