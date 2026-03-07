import re
import json


def extract_json_block(text: str) -> dict | list:
    """Parse a JSON object or array from an LLM response that may include Markdown formatting.

    Gemini sometimes wraps responses in ```json ... ``` fences. This strips them
    before parsing so downstream code always gets clean Python objects.

    Args:
        text: Raw response string from Gemini or any LLM.

    Returns:
        Parsed JSON as a dict or list.

    Raises:
        ValueError: If no valid JSON block is found.
    """
    cleaned = re.sub(r"```json|```", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from LLM output: {e}\n\nRaw text:\n{text[:500]}")
