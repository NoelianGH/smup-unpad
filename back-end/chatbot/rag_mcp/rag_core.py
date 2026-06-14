import os
import json
import numpy as np
from pathlib import Path
from collections import deque
from dotenv import load_dotenv
from groq import Groq
from sentence_transformers import SentenceTransformer

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
HISTORY = deque(maxlen=5)

def get_embedding(text):
    try:
        emb = embedding_model.encode(text, normalize_embeddings=True)
        return np.array(emb, dtype=np.float32)
    except:
        return np.zeros(EMBEDDING_DIM, dtype=np.float32)

def cosine_similarity(a, b):
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def load_and_index_documents(folder_path="doc/pages", cache_path="doc/embeddings_cache.json"):
    global INDEXED_DOCS
    folder = Path(folder_path)
    os.makedirs(folder_path, exist_ok=True)

    cache = {}
    if os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path, "r"))
        except:
            pass

    new_docs = []
    files = list(folder.glob("*.txt"))

    for file in files:
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

        new_docs.append({
            "filename": file.name,
            "text": text,
            "embedding": emb,
        })

    json.dump(cache, open(cache_path, "w"))
    INDEXED_DOCS = new_docs

def retrieve_docs(question, k=3):
    if not INDEXED_DOCS:
        return []

    q_emb = get_embedding(question)
    if np.all(q_emb == 0):
        return []

    scored = [(cosine_similarity(q_emb, d["embedding"]), d) for d in INDEXED_DOCS]
    scored.sort(reverse=True, key=lambda x: x[0])
    return [d for score, d in scored[:k]]

def run_rag(question):
    if not INDEXED_DOCS:
        load_and_index_documents()

    docs = retrieve_docs(question, k=3)
    if not docs:
        return "Tidak ditemukan dokumen relevan."

    context = "\n\n".join([f"Sumber: {d['filename']}\n{d['text']}" for d in docs])
    history_text = "\n".join([f"User: {h['q']}\nBot: {h['a']}" for h in HISTORY])

    prompt = f"""
Gunakan konteks berikut untuk menjawab pertanyaan:

RIWAYAT:
{history_text}

KONTEN:
{context}

PERTANYAAN:
{question}

Jawab dalam Bahasa Indonesia.
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",  # Bisa diganti: mixtral-8x7b-32768, gemma2-9b-it, dll
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1024,
    )
    answer = response.choices[0].message.content

    HISTORY.append({"q": question, "a": answer})
    return answer
