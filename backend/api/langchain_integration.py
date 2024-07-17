import os
from langchain_ai21 import ChatAI21
from langchain_core.prompts import ChatPromptTemplate

# Set the environment variable
os.environ["AI21_API_KEY"] = "KBtGHWprJBAmVuBVbmNvMOiZbPLbv135"

# Verify the API key
assert os.environ.get("AI21_API_KEY") is not None, "API key not set"

def get_jamba_response(query, context):
    chat = ChatAI21(model="jamba-instruct")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a helpful assistant that analyzes codebases."),
            ("human", f"Describe the data flow in this codebase. {query} Context: {context}")
        ]
    )
    chain = prompt | chat
    try:
        response = chain.invoke({"query": query})
        return response
    except Exception as e:
        print(f"Error invoking LangChain: {e}")
        return None

# Test the integration
if __name__ == "__main__":
    query = "Where does data flow through the gateway?"
    context = "Example codebase context"
    response = get_jamba_response(query, context)
    if response:
        print(response)
    else:
        print("Failed to get a response from the model.")
