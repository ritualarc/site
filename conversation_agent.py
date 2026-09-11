"""The tool-calling agent behind the member "Conversation" tab.

Built the same way as the Vercel AI Gateway is used elsewhere in this app
(ai_analysis.py): a plain ChatOpenAI pointed at the Gateway's OpenAI-compatible
endpoint, so AI_MODEL can be any Gateway model string — including a Google
model — with no code change here.
"""

import logging
import os

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from account_store import AccountStoreError, append_conversation_message, get_recent_conversation_messages
from agent_tools import get_matching, get_weather

logger = logging.getLogger(__name__)

AI_GATEWAY_API_KEY = os.environ.get("AI_GATEWAY_API_KEY")
AI_MODEL = os.environ.get("AI_MODEL")

CONVERSATION_CONFIGURED = bool(AI_GATEWAY_API_KEY and AI_MODEL)

# How many prior messages (user + assistant turns combined) to load as memory for each call.
MAX_HISTORY_MESSAGES = 20

_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"

TOOLS = [get_matching, get_weather]

SYSTEM_PROMPT = (
    "You are Ritual Arc's member assistant. Help the member with questions about "
    "what to wear, their wardrobe, and the weather, using the tools available to "
    "you whenever they help answer the question. Keep replies short and friendly."
)

_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("placeholder", "{chat_history}"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

_agent_executor = None
if CONVERSATION_CONFIGURED:
    _llm = ChatOpenAI(
        model=AI_MODEL,
        api_key=AI_GATEWAY_API_KEY,
        base_url=_GATEWAY_BASE_URL,
        temperature=0,
        timeout=90,
    )
    _agent = create_tool_calling_agent(_llm, TOOLS, _prompt)
    _agent_executor = AgentExecutor(agent=_agent, tools=TOOLS)


class ConversationError(RuntimeError):
    pass


async def ask(email: str | None, message: str) -> str:
    """Run one turn of the conversation agent, with memory of the member's past turns.

    History is loaded from and saved back to the Neon database (account_store.py),
    keyed by the member's email the same way brand profiles and account type are.
    If email is missing, or the database isn't configured/reachable, the call still
    goes through — it just degrades to a single stateless turn with no memory.
    """
    if not CONVERSATION_CONFIGURED:
        raise ConversationError("AI_GATEWAY_API_KEY and AI_MODEL must be set to use the conversation agent.")

    chat_history = []
    if email:
        try:
            recent = await get_recent_conversation_messages(email, limit=MAX_HISTORY_MESSAGES)
            for item in recent:
                if item["role"] == "assistant":
                    chat_history.append(AIMessage(content=item["content"]))
                else:
                    chat_history.append(HumanMessage(content=item["content"]))
        except AccountStoreError:
            logger.exception("Failed to load conversation history; continuing without memory")

    try:
        result = await _agent_executor.ainvoke({"input": message, "chat_history": chat_history})
    except Exception as exc:
        raise ConversationError(f"Conversation agent request failed: {exc}") from exc

    reply = result.get("output", "")

    if email:
        try:
            await append_conversation_message(email, "user", message)
            await append_conversation_message(email, "assistant", reply)
        except AccountStoreError:
            logger.exception("Failed to save conversation message; this turn won't be remembered")

    return reply
