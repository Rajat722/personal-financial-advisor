from newspaper import Article

# === EXTRACT ARTICLE TEXT ===
def extract_article_text(url):
    article = Article(url)
    article.download()
    article.parse()
    return article.text

url = "https://www.dailysabah.com/business/defense/turkiyes-akinci-ucav-completes-firing-test-with-domestic-guidance-kit"
print(extract_article_text(url=url))

import re
import json

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
