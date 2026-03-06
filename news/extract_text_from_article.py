import re
import json
from newspaper import Article


def extract_article_text(url: str) -> str:
    """Download and parse the full text of an article from its URL."""
    article = Article(url)
    article.download()
    article.parse()
    return article.text

def extract_json_block(text):
    """
    Extracts and parses a JSON object from an LLM response that may include Markdown formatting.

    Args:
        text (str): Raw response from Gemini or any LLM.

    Returns:
        dict: Parsed JSON object.

    Raises:
        ValueError: If valid JSON block not found.
    """
    # Remove triple backticks and 'json' labels if present
    cleaned = re.sub(r"```json|```", "", text.strip())
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from Gemini output: {e}")
