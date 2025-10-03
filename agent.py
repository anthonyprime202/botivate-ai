from typing import List, TypedDict
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from langgraph.graph import StateGraph, END
from sqlalchemy import create_engine
from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()

class DatabaseQuery(BaseModel):
    """The user is asking a question that requires a database query, or can be solved by an sql query"""
    pass

class Conversation(BaseModel):
    """The user is greeting, making a small talk or asking a general knowledge question not related to database or cannot be handled with sql."""
    pass


class AgentState(TypedDict):
    question: str
    chat_history: List[BaseMessage]
    query: str 
    result: str
    answer: str
    retries: int
    intent: str

engine = create_engine("sqlite:///sheets.db")
db = SQLDatabase(engine=engine) 
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
execute_query_tool = QuerySQLDatabaseTool(db=db)

@tool
def get_current_datetime() -> str:
    """Returns today's date and the current time in ISO 8601 format."""
    return datetime.now().isoformat()

def classify_intent_node(state: AgentState):
    """Classifies the user's question by forcing the LLM to call a specific tool."""
    print("--- Classifying Intent (with Function Calling) ---")

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an intent classifier. Call the appropriate tool based on the user's last message."),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}")
    ])

    tools = [DatabaseQuery, Conversation]
    llm_with_tools = llm.bind_tools(tools)
    runnable = prompt | llm_with_tools

    ai_message = runnable.invoke({
        "question": state['question'],
        "chat_history": state.get("chat_history", []),
    })

    if not ai_message.tool_calls:
        intent = "Conversation"
    else:
        intent = ai_message.tool_calls[0]['name']
    
    print(f"Intent: {intent}")
    return {'intent': intent}

def decide_intent_path(state: AgentState): 
    if state["intent"] == "DatabaseQuery":
        return "generate_query"
    else: 
        return "handle_conversation"

def handle_conversation_node(state: AgentState):
    """Creates natural conversation with the user"""

    print("--- Handling Conversation ---")

    prompt = ChatPromptTemplate.from_messages([
        ('system', "You are a friendly assisstant. Reply the user politely, with a relevant response."),
        MessagesPlaceholder(variable_name="chat_history"),
        ('human', "{question}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])

    tools = [get_current_datetime]

    agent_runnable = create_openai_functions_agent(llm, tools, prompt)

    agent_excutor = AgentExecutor(agent=agent_runnable, tools=tools, verbose=True)

    answer = agent_excutor.invoke({
        "question": state["question"],
        "chat_history": state.get("chat_history", [])
    })
    print(f"Final Answer: {answer['output']}")
    return {"answer": answer['output']}

def generate_query_node(state: AgentState):
    """
    Takes the user's question and chat history, generates a SQL query,
    and adds it to the state.
    """

    print("--- Generating SQL Query ---")

    system_prompt = """You are an AI expert in writing SQLite queries.
    Given a user question and conversation history, create a syntactically correct SQLite query.
    {schema}
    
    --- Data Dictionary ---
    - The "Status" column: 'Completed', 'Yes', 'Done' all mean the task is complete.
    - The "Priority" column: 'High', 'Urgent', 'H' all mean high priority. 'Low' and 'L' mean low priority.
    - The "Assignee" column: Usernames like 'john.doe' and 'johnd' should be treated as the same person.
    -----------------------

    - Only return the SQL query. Do not add any other text or explaination.
    - **IMPORTANT:** If a column name contains a space, you MUST wrap it in double quotes. For example: "Task Description".
    """

    if "Error:" in state.get('result', ''):

        system_prompt += """
        \n---
        The previous query you wrote failed. Here is the error message: 
        {error}
        Please look at the error message, the schema, and the user's question, and write a new corrected SQL query
        ---
        """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}")
    ])

    runnable = prompt | llm

    raw_query = runnable.invoke({
        "question": state['question'],
        "chat_history": state.get("chat_history", []),
        "schema": db.get_table_info(),
        "error": state.get("result", '')
    }).content

    sql_query = raw_query.strip().replace("```sql", "").replace("```", "").strip()

    print(f"Generated Query: {sql_query}")
    retries = state.get("retries", 0)

    return {"query": sql_query, "retries": retries + 1}

def execute_query_node(state: AgentState):
    """Executes the SQL query and returns the result."""

    print("--- Executing SQL Query ---")

    query = state['query']
    result = execute_query_tool.invoke(query)
    print(f"Query Result: {result}")
    return {"result": result}

def decide_result_status(state: AgentState):
    """Checks the result for an error and decides the next step."""
    if "Error:" in state["result"]:
        print("--- Query failed. Looping back to generate a new query. ---")
        if state['retries'] > 7:
            print("--- 🚫 Max retries reached. Handling error. ---")
            return "handle_error"
        else:
            return "generate_query"
    else: 
        return "summarize_result"
    
def handle_error_node(state: AgentState):
    """This node is called when the agent gives up."""
    print("--- 😩 Agent failed after multiple retries ---")
    question = state['question']
    error = state.get("result", "Unknown error")
    query = state['query']

    error_prompt = ChatPromptTemplate.from_messages([
        ('system', "You are a helpful AI assistant the runs SQL database queries. Even after mulitple tries the query generated fails, address how the user should adjust there question so it can give valid results."),
        ('human', """Based on the user's question: "{question}"
        The following SQL  was generated: "{query}"
        And here is the error: "{error}"

        Please provide a clear, natural language answer.""")
    ])

    runnable = error_prompt | llm 

    answer = runnable.invoke({
        "question": question,
        "query": query,
        "error": error
    }).content 

    print(f"Final Answer: {answer}")
    return {"answer": answer}

def summarize_result_node(state: AgentState):
    """Takes the query result and the user's question and creates a natural language answer"""

    print("--- Summarizing Result ---")
    question = state['question']
    result = state['result']
    query = state['query']

    summarizer_prompt = ChatPromptTemplate.from_messages([
        ('system', "You are a helpful AI assistant. Your job is to answer the user's question based on the data provided."),
        ('human', """Based on the user's question: "{question}"
        The following SQL query was generated: "{query}"
        And here is the result from the database: "{result}"

        Please provide a clear, natural language answer.""")
    ])

    runnable = summarizer_prompt | llm 

    answer = runnable.invoke({
        "question": question,
        "query": query,
        "result": result
    }).content 

    print(f"Final Answer: {answer}")
    return {"answer": answer}


graph = (StateGraph(AgentState)
         .add_node("classify_intent", classify_intent_node)
         .add_node("handle_conversation", handle_conversation_node)
         .add_node("generate_query", generate_query_node)
         .add_node("execute_query", execute_query_node)
         .add_node("summarize_result", summarize_result_node)
         .add_node("handle_error", handle_error_node)
        
         .set_entry_point("classify_intent")
         .add_conditional_edges(
             source="classify_intent",
             path=decide_intent_path,
             path_map={
                 "generate_query": "generate_query",
                 "handle_conversation": "handle_conversation"
             }
         )
         .add_edge("generate_query", "execute_query")
         .add_conditional_edges(
             source="execute_query",
             path=decide_result_status,
             path_map={
                 "generate_query": "generate_query",
                 "summarize_result": "summarize_result",
                 "handle_error": "handle_error",
             }
         )
         .add_edge("handle_conversation", END)
         .add_edge("handle_error", END)
         .add_edge("summarize_result", END)
         .compile())

initial_state = {
    "question": "Aaj kya date?",
    "chat_history": []
}

if __name__ == "__main__":
    final_state = graph.invoke(initial_state)

    print("\n--- Final State ---")
    print(final_state["answer"])