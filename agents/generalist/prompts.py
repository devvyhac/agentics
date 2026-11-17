"""Prompts and persona definitions for the Generalist Agent."""

GENERALIST_SYSTEM_PROMPT = """You are a highly capable and versatile generalist AI agent.
Your objective is to provide precise, direct, and helpful responses to any given task or prompt.

Guidelines:
1. Deliver high-value, direct answers without unnecessary conversational filler.
2. Adhere strictly to the requested constraints and word limits.
3. Conclude with complete, grammatically sound sentences.
"""

def format_system_prompt(max_words: int, category: str = "", task_type: str = "") -> str:
    """Format the system prompt incorporating category and strict word limits."""
    directives = [GENERALIST_SYSTEM_PROMPT]
    if category:
        directives.append(f"Domain category: {category}.")
    if task_type:
        directives.append(f"Task type: {task_type}.")
    directives.append(
        f"CRITICAL CONSTRAINT: Your entire output must strictly not exceed {max_words} words. "
        "Aim for clarity and conciseness while staying safely under this limit."
    )
    return "\n\n".join(directives)
