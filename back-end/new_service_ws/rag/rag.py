import os
import numpy as np
from dotenv import load_dotenv
from pathlib import Path
import json
import re
from collections import deque
from natsort import natsorted
from groq import Groq
from sentence_transformers import SentenceTransformer
import nltk
from nltk.corpus import wordnet as wn
from nltk.tokenize import word_tokenize

try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('tokenizers/punkt_tab')
    nltk.data.find('corpora/wordnet')
    nltk.data.find('corpora/omw-1.4')
except LookupError:
    print("Downloading NLTK data...")
    nltk.download('punkt')
    nltk.download('punkt_tab')
    nltk.download('wordnet')
    nltk.download('omw-1.4')

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    print("WARNING: GROQ_API_KEY not found in .env")

client = Groq(api_key=api_key)

print("Loading embedding model...")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
EMBEDDING_DIM = 384
print("Embedding model loaded.")

INDEXED_DOCS = []
URL_HISTORY = {}
CHAT_HISTORY = deque(maxlen=5)

def get_embedding(text):
    try:
        emb = embedding_model.encode(text, normalize_embeddings=True)
        return np.array(emb, dtype=np.float32)
    except Exception as e:
        print(f"Error embedding: {e}")
        return np.zeros(EMBEDDING_DIM, dtype=np.float32)

def cosine_similarity(a, b):
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return np.dot(a, b) / (norm_a * norm_b)

def load_url_history(path="./scrapping/doc/urlHistory.txt"):
    url_map = {}
    if not os.path.exists(path):
        print(f"WARNING: File {path} tidak ditemukan.")
        return url_map
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "|" in line:
                    parts = line.strip().split("|", 1)
                    if len(parts) == 2:
                        url_map[parts[0].strip()] = parts[1].strip()
        print(f"--- URL History Loaded: {len(url_map)} entries ---")
    except Exception as e:
        print(f"Error loading URL history: {e}")
    return url_map

def load_and_index_documents(folder_path="./scrapping/doc/pages", cache_path="./scrapping/doc/embeddings_cache.json"):
    global INDEXED_DOCS, URL_HISTORY
    URL_HISTORY = load_url_history()
    print(f"\n--- Memulai Indexing dari: {folder_path} ---")
    folder = Path(folder_path)
    if not folder.exists():
        os.makedirs(folder_path, exist_ok=True)
        INDEXED_DOCS = []
        return
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except:
            pass
    new_docs = []
    files = natsorted(list(folder.glob("*.txt")), key=lambda x: x.name)
    for i, file in enumerate(files):
        try:
            text = file.read_text(encoding="utf-8").strip()
            if not text:
                continue
            mtime = os.path.getmtime(file)
            key = f"{file.name}:{mtime}"
            if key in cache:
                emb = np.array(cache[key], dtype=np.float32)
            else:
                emb = get_embedding(text)
                cache[key] = emb.tolist()
            tokens = set(word_tokenize(text.lower()))
            new_docs.append({"id": f"DOC_{i}", "filename": file.name, "text": text, "tokens": tokens, "embedding": emb})
        except Exception as e:
            print(f"Skip {file.name}: {e}")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except:
        pass
    INDEXED_DOCS = new_docs
    print(f"--- Selesai! {len(INDEXED_DOCS)} dokumen terindeks. ---")

def format_answer_with_sources(answer_text, docs):
    found_urls = set()
    for doc in docs:
        fname = doc.get('filename')
        if fname and fname in URL_HISTORY:
            found_urls.add(URL_HISTORY[fname])
    for doc in docs:
        urls = re.findall(r'(?:URL|Url|page ini|link)\s*:?\s*(https?://\S+)', doc.get('text', ''))
        for url in urls:
            found_urls.add(url.rstrip('.,;)'))
    clean_answer = answer_text.replace("```html", "").replace("```", "")
    if found_urls:
        items = "".join([f'<li><a href="{u}" target="_blank" style="color:#2563eb;text-decoration:underline;">{u}</a></li>' for u in found_urls])
        clean_answer += f'<br><hr style="border-top:1px solid #e5e7eb;margin:16px 0;"><p><strong>Sumber Referensi:</strong></p><ul>{items}</ul>'
    return clean_answer

def retrieve_by_embedding(question, k=5):
    if not INDEXED_DOCS:
        return []
    try:
        q_emb = get_embedding(question)
        if np.all(q_emb == 0):
            return []
        scored = [(cosine_similarity(q_emb, doc["embedding"]), doc) for doc in INDEXED_DOCS]
        scored.sort(reverse=True, key=lambda x: x[0])
        return [doc for _, doc in scored[:k]]
    except:
        return []

def retrieve_by_wordnet(question, k=5):
    if not INDEXED_DOCS:
        return []
    q_tokens = word_tokenize(question.lower())
    expanded = set(q_tokens)
    for token in q_tokens:
        for syn in wn.synsets(token, lang='ind'):
            for lemma in syn.lemmas(lang='ind'):
                expanded.add(lemma.name().lower().replace('_', ' '))
    scored = []
    for doc in INDEXED_DOCS:
        count = len(doc["tokens"].intersection(expanded))
        if count > 0:
            scored.append((count, doc))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [doc for _, doc in scored[:k]]

def call_groq(messages, temperature=0.3, max_tokens=1024):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content

def rerank_docs(question, combined_docs):
    docs_str = "\n".join([f"ID: {d['id']}\nCuplikan: {d['text'][:300]}...\n" for d in combined_docs])
    prompt = f"Pilih maksimal 3 ID dokumen paling relevan. HANYA kembalikan ID dipisahkan koma (contoh: DOC_2, DOC_5). Jika tidak ada: NONE\n\nPERTANYAAN: {question}\n\nDAFTAR DOKUMEN:\n{docs_str}\n\nOUTPUT ID:"
    try:
        result = call_groq([{"role": "user", "content": prompt}], max_tokens=50)
        relevant_ids = [x.strip() for x in result.split(',')]
        final_docs = [d for d in combined_docs if d['id'] in relevant_ids]
        return final_docs if final_docs else None
    except Exception as e:
        print(f"Reranking Error: {e}")
        return None

def mainrag0(history, question, ocr_text=None):
    return f"<p>RAG belum diinisialisasi. {question} dengan OCR : {ocr_text}</p>"

def _build_messages(history, context, question):
    system_prompt = """Anda adalah asisten AI untuk Universitas Padjadjaran (Unpad). Jawablah berdasarkan dokumen terpilih.
FORMAT: HTML valid tanpa ```html. Gunakan <p>, <ul>/<li>, <ol>/<li>, <table>. Jangan Markdown.
Jika tidak ada info: <p>Maaf, informasi tidak ditemukan dalam dokumen.</p>"""
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": "user", "content": turn["q"]})
        messages.append({"role": "assistant", "content": turn["a"]})
    messages.append({"role": "user", "content": f"KONTEKS:\n{context}\n\nPERTANYAAN: {question}"})
    return messages

def mainrag(history, question):
    global INDEXED_DOCS
    if not INDEXED_DOCS:
        load_and_index_documents()
    print(f"\nProcessing: {question}")
    docs_emb = retrieve_by_embedding(question, k=5)
    docs_wn = retrieve_by_wordnet(question, k=5)
    combined_docs = list({d['id']: d for d in (docs_emb + docs_wn)}.values())
    if not combined_docs:
        return "<p>Maaf, tidak ditemukan informasi yang relevan.</p>"
    print("--- Reranking via Groq ---")
    final_docs = rerank_docs(question, combined_docs) or docs_emb[:3]
    context = "\n\n".join([f"Sumber: {d['filename']}\nIsi: {d['text']}" for d in final_docs])
    chat_history = list(history) if history else list(CHAT_HISTORY)
    messages = _build_messages(chat_history, context, question)
    try:
        answer = call_groq(messages)
        CHAT_HISTORY.append({"q": question, "a": answer})
        return format_answer_with_sources(answer, final_docs)
    except Exception as e:
        return f"<p>Error: {str(e)}</p>"

def mainragocr(history, question, ocr_text=None):
    global INDEXED_DOCS
    if not INDEXED_DOCS:
        load_and_index_documents()
    print(f"\nProcessing OCR RAG: {question}")
    q = question + (f"\n[OCR]:\n{ocr_text}" if ocr_text else "")
    docs_emb = retrieve_by_embedding(q, k=5)
    docs_wn = retrieve_by_wordnet(q, k=5)
    combined_docs = list({d['id']: d for d in (docs_emb + docs_wn)}.values())
    if not combined_docs:
        return "<p>Maaf, tidak ditemukan informasi yang relevan.</p>"
    final_docs = rerank_docs(q, combined_docs) or docs_emb[:3]
    context = "\n\n".join([f"Sumber: {d['filename']}\nIsi: {d['text']}" for d in final_docs])
    chat_history = list(history) if history else list(CHAT_HISTORY)
    messages = _build_messages(chat_history, context, q)
    try:
        answer = call_groq(messages)
        CHAT_HISTORY.append({"q": question, "a": answer})
        return format_answer_with_sources(answer, final_docs)
    except Exception as e:
        return f"<p>Error: {str(e)}</p>"

def reload_rag():
    load_and_index_documents()
    CHAT_HISTORY.clear()