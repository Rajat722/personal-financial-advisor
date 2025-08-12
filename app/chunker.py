from transformers import AutoTokenizer

class Chunker:
    def __init__(self, model_name="bert-base-uncased", max_tokens=500, overlap=50):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.MAX_TOKENS = max_tokens
        self.OVERLAP = overlap

    def chunk(self, text):
        paragraphs = self.split_into_paragraphs(text)
        chunks = self.semantic_chunk_paragraphs(paragraphs, self.MAX_TOKENS, self.OVERLAP)
        return chunks

    def estimate_tokens(self, text):
        return len(self.tokenizer.tokenize(text))

    def split_into_paragraphs(self, text):
        paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 0]
        if len(paragraphs) <= 1:
            # Fallback to sentence splitting if not enough paragraphs
            paragraphs = [sent.text.strip() for sent in self.nlp(text).sents if len(sent.text.strip()) > 0]
        return paragraphs

    def semantic_chunk_paragraphs(self, paragraphs, max_tokens, overlap):
        chunks = []
        current_chunk = []
        current_token_count = 0

        for paragraph in paragraphs:
            tokens = self.estimate_tokens(paragraph)
            print("Tokens: ", tokens)
            if tokens > max_tokens:
                # Split long paragraph into sentences using spaCy
                sentences = [sent.text.strip() for sent in self.nlp(paragraph).sents if sent.text.strip()]
                for sent in sentences:
                    sent_tokens = self.estimate_tokens(sent)
                    if current_token_count + sent_tokens > max_tokens:
                        chunks.append(" ".join(current_chunk))
                        current_chunk = current_chunk[-overlap:] if overlap else []
                        current_token_count = sum(self.estimate_tokens(s) for s in current_chunk)
                    current_chunk.append(sent)
                    current_token_count += sent_tokens
            else:
                if current_token_count + tokens > max_tokens:
                    chunk = " ".join(current_chunk)
                    chunks.append(chunk)
                    print("overlap", paragraph)
                    current_chunk = []
                    current_token_count = tokens
                current_chunk.append(paragraph)
                current_token_count += tokens

        if current_chunk:
            chunks.append(" ".join(current_chunk))
        return chunks
