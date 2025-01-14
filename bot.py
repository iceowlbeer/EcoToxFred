import plotly
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
import asyncio

from utils import get_version
from graph_agent import GraphEcoToxFredAgent
from astream_events_handler import invoke_our_graph

about_text = f"""
**EcoToxFred v{get_version()}** — a Neo4j-backed Chatbot discussing environmental monitoring and hazard data.

Contact:
  - Jana Schor jana.schor@ufz.de
  - Patrick Scheibe pscheibe@cbs.mpg.de

EcoToxFred may occasionally provide incorrect or incomplete information.
Always carefully verify the returned results before relying on them.
"""

st.set_page_config(page_title="EcoToxFred", page_icon="figures/assistant.png",
                   layout='centered',
                   menu_items={"about": about_text})

example_questions = [
    "EcoToxFred, what is your expertise? Structure your response in bullet points.",
    "What is Diuron and where has it been measured?",
    "What is Triclosan? Has it been measured in European freshwater?",
    "Show the ratioTU distribution for algae along the Danube (2010–2015).",
    "Find the 10 most frequent multiple risk drivers.",
    "For Citalopram, provide the name of the sampling site and the measurement time point as a table?"
]

# Set up the session state and initialize the LLM agent
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.chat_agent = GraphEcoToxFredAgent()
    st.session_state.messages = [AIMessage(content="Hi, I'm EcoToxFred!  How can I help you?")]
    st.session_state.figure_numbers = 0
    st.session_state.example_question = None


def generate_response(query: str):
    """
    Generates a chat assistant's response based on the user-provided query, updates
    the application's session state with messages, and renders the response in the user interface.
    :param query: The user's input message that will be processed and sent to the chat assistant.
    """
    st.session_state.messages.append(HumanMessage(content=query))
    st.chat_message("user", avatar="figures/user.png").write(query)

    with st.chat_message("assistant", avatar="figures/assistant.png"):
        # create a placeholder container for streaming and any other events to visually render here
        placeholder = st.container()
        try:
            response = asyncio.run(invoke_our_graph(
                st.session_state.chat_agent,
                st.session_state.messages,
                placeholder))
            st.session_state.messages.append(response)
        except Exception as e:
            print(f'[OpenAI API] {e}')
            st.session_state.messages.append(AIMessage(
                content=f"There was an OpenAI API connection error: {e}. "
                        f"This may happen if you hit OpenAI API's rate limit "
                        f"(the number of request send in a specific time interval)."
                        f"Please try again in a few seconds."))


def handle_example_question(example_question):
    st.session_state.example_question = example_question


with st.sidebar:
    st.image("figures/UFZ_MPG_Logo.svg")
    st.header(f"EcoToxFred (v{get_version()})", divider=True)
    st.markdown(
        "A Chatbot for discussing environmental monitoring and hazard "
        "data collected in a large knowledge graph and stored in a Neo4j Graph Database."
    )
    st.header("Example Questions", divider=True)
    for index, example_question in enumerate(example_questions):
        st.button(
            example_question,
            key=f"example_question_{index}",
            on_click=handle_example_question,
            args=[example_question]
        )

# Display messages in Session State
for msg in st.session_state.messages:
    # https://docs.streamlit.io/develop/api-reference/chat/st.chat_message
    # we store them as AIMessage and HumanMessage as its easier to send to LangGraph
    if isinstance(msg, AIMessage):
        with st.chat_message("assistant", avatar="figures/assistant.png"):
            if "artifact" in msg.model_extra.keys():
                st.session_state.figure_numbers += 1
                fig = plotly.io.from_json(msg.artifact)
                st.plotly_chart(
                    fig,
                    key=f"plotly_chart_{st.session_state.figure_numbers:04d}",
                    use_container_width=True,
                    config={'displayModeBar': False})
            st.write(msg.content)
    elif isinstance(msg, HumanMessage):
        st.chat_message("user", avatar="figures/user.png").write(msg.content)

# If an example button was pressed, we use this as input and generate a response.
if st.session_state.example_question:
    generate_response(st.session_state.example_question)
    st.session_state.example_question = None

# Here the user can type in a question that gets answered.
question = st.chat_input()
if question:
    generate_response(question)
