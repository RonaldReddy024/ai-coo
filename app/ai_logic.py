import os
from typing import Any, Dict

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def build_ai_coo_prompt(title: str, metadata: Dict[str, Any]) -> str:
    """
    Turn a task title + metadata into a rich prompt for the AI COO.
    """
    meta_lines = []
    for k, v in (metadata or {}).items():
        meta_lines.append(f"- {k}: {v}")
    meta_block = "\n".join(meta_lines) if meta_lines else "None"

    prompt = f"""
You are an AI COO helping an operations team execute tasks.

Task:
- Title: {title}

Context / metadata:
{meta_block}

Your job:
1. Interpret what this task actually means in a business/ops context.
2. Break it down into 3–7 clear, actionable steps.
3. Flag any assumptions you had to make.
4. Suggest what data or tools you would want to query or use.

Return your answer in this JSON-like bullet format (NOT raw JSON, just bullets):

Summary: <one sentence summary>
Steps:
- <step 1>
- <step 2>
Risks:
- <risk 1>
DataNeeded:
- <data or systems you'd query>
    """.strip()

    return prompt


def run_ai_coo_logic(task) -> str:
    """
    Real AI COO brain: call an LLM with a structured prompt and
    return a human-readable result_text.

    `task` is your SQLAlchemy Task model instance.
    """
    title = getattr(task, "title", "")
    metadata = getattr(task, "metadata_json", {}) or {}

    prompt = build_ai_coo_prompt(title, metadata)

    # Call the LLM
    response = client.chat.completions.create(
        model="gpt-4.1-mini",  # or any other model you have access to
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an AI COO, an expert in operations, process design, "
                    "and executive decision support. Be concise but concrete."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=400,
    )

    content = response.choices[0].message.content.strip()
    # This will be stored in Task.result_text
    return content
