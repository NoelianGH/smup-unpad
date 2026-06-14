import os
import numpy as np
from dotenv import load_dotenv
from pathlib import Path
import json
import re
from collections import Counter
from groq import Groq

# --- IMPORT LANGCHAIN ---
from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferWindowMemory
from langchain.chains import LLMChain

# --- IMPORT SENTENCE TRANSFORMERS (untuk Embedding lokal) ---
from sentence_transformers import SentenceTransformer

# --- IMPORT NLTK (WORDNET) ---
import nltk
from nltk.corpus import wordnet as wn
from nltk.tokenize import word_tokenize

# Setup NLTK
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
    print("NLTK data downloaded.")

# 1. Load environment variables
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    print("WARNING: GROQ_API_KEY not found in .env")

# --- EMBEDDING MODEL (lokal, tidak butuh API key) ---
print("Loading embedding model...")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
EMBEDDING_DIM = 384
print("Embedding model loaded.")

# --- GLOBAL VARIABLES ---
INDEXED_DOCS = []

# --- LANGCHAIN SETUP ---

# Model Utama (Groq)
llm = ChatGroq(
    model="llama-3.3-70b-versatile",  # Bisa diganti: mixtral-8x7b-32768, gemma2-9b-it, dll
    groq_api_key=api_key,
    temperature=0.3,
    timeout=60,
)

# A. Setup Memory
memory = ConversationBufferWindowMemory(
    k=5,
    memory_key="chat_history",
    input_key="question"
)

# B. Setup Prompt Reranking
rerank_template = """
Anda adalah sistem penilai relevansi dokumen.
Diberikan pertanyaan pengguna dan daftar kutipan dokumen, tugas Anda adalah memilih dokumen mana yang paling relevan untuk menjawab pertanyaan tersebut.

PERTANYAAN: {question}

DAFTAR DOKUMEN:
{docs_list}

INSTRUKSI:
1. Analisis relevansi setiap dokumen terhadap pertanyaan.
2. Pilih maksimal 3 ID dokumen yang paling relevan (misal: DOC_1, DOC_3).
3. Urutkan dari yang paling relevan.
4. HANYA kembalikan ID dokumen dipisahkan koma. Contoh: DOC_2, DOC_5, DOC_1
5. Jika tidak ada yang relevan, kembalikan: NONE

OUTPUT ID:
"""
rerank_prompt = PromptTemplate(
    input_variables=["question", "docs_list"],
    template=rerank_template
)
rerank_chain = LLMChain(llm=llm, prompt=rerank_prompt)

# C. Setup Prompt Jawaban Akhir (Format HTML)
qa_template = """
Anda adalah asisten AI untuk Universitas Padjadjaran (Unpad).
Jawablah pertanyaan berdasarkan dokumen terpilih di bawah ini.

KONTEKS:
{context}

RIWAYAT:
{chat_history}

PERTANYAAN: {question}

⚙️ ATURAN FORMAT (STRICT HTML):
1. Gunakan tag HTML murni: <p>, <ul>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>.
2. JANGAN gunakan Markdown sama sekali (jangan pakai **, ##, atau tabel markdown).
3. JANGAN membungkus jawaban dengan ```html atau ``` (code block). Langsung berikan tag HTML-nya.
4. Untuk Tabel:
   - Gunakan struktur lengkap: <table> <thead> <tr> <th>...</th> </tr> </thead> <tbody> <tr> <td>...</td> </tr> </tbody> </table>.
   - Jangan lupa tutup tag tabelnya.
   
JAWABAN (HTML Murni):
"""

qa_prompt = PromptTemplate(
    input_variables=["chat_history", "context", "question"],
    template=qa_template
)
qa_chain = LLMChain(llm=llm, prompt=qa_prompt, memory=memory)


# --- FUNGSI UTILITY ---

# 1. Embedding (menggunakan SentenceTransformer lokal)
def get_embedding(text):
    try:
        emb = embedding_model.encode(text, normalize_embeddings=True)
        return np.array(emb, dtype=np.float32)
    except Exception as e:
        print(f"Error embedding: {e}")
        return np.zeros(EMBEDDING_DIM, dtype=np.float32)

# 2. Cosine Similarity
def cosine_similarity(a, b):
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return np.dot(a, b) / (norm_a * norm_b)

# 3. Load & Index
def load_and_index_documents(folder_path="doc/pages", cache_path="doc/embeddings_cache.json"):
    global INDEXED_DOCS
    print(f"\n--- Memulai Indexing Dokumen dari: {folder_path} ---")

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
        except Exception:
            pass

    new_docs = []
    files = list(folder.glob("*.txt"))

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

            new_docs.append({
                "id": f"DOC_{i}",
                "filename": file.name,
                "text": text,
                "tokens": tokens,
                "embedding": emb
            })
        except Exception as e:
            print(f"Skip {file.name}: {e}")

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except:
        pass

    INDEXED_DOCS = new_docs
    print(f"--- Selesai! {len(INDEXED_DOCS)} dokumen terindeks. ---")


# --- RETRIEVAL ENGINE ---

# A. Retrieval via Embedding (Semantic)
def retrieve_by_embedding(question, k=5):
    if not INDEXED_DOCS:
        return []
    try:
        q_emb = get_embedding(question)
        if np.all(q_emb == 0):
            return []

        scored = []
        for doc in INDEXED_DOCS:
            score = cosine_similarity(q_emb, doc["embedding"])
            scored.append((score, doc))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [doc for score, doc in scored[:k]]
    except:
        return []

# B. Retrieval via WordNet/Keyword (Lexical)
def retrieve_by_wordnet(question, k=5):
    if not INDEXED_DOCS:
        return []

    q_tokens = word_tokenize(question.lower())

    expanded_keywords = set(q_tokens)
    for token in q_tokens:
        synsets = wn.synsets(token, lang='ind')
        for syn in synsets:
            for lemma in syn.lemmas(lang='ind'):
                expanded_keywords.add(lemma.name().lower().replace('_', ' '))

    scored = []
    for doc in INDEXED_DOCS:
        doc_tokens = doc["tokens"]
        match_count = len(doc_tokens.intersection(expanded_keywords))
        if match_count > 0:
            scored.append((match_count, doc))

    scored.sort(reverse=True, key=lambda x: x[0])
    return [doc for score, doc in scored[:k]]


# --- MAIN RAG LOGIC ---

def mainrag(question):
    global INDEXED_DOCS
    if not INDEXED_DOCS:
        load_and_index_documents()

    print(f"\nProcessing: {question}")

    # 1. HYBRID RETRIEVAL (Embedding + WordNet)
    docs_emb = retrieve_by_embedding(question, k=5)
    docs_wn = retrieve_by_wordnet(question, k=5)

    combined_docs = list({d['id']: d for d in (docs_emb + docs_wn)}.values())

    if not combined_docs:
        return "<p>Maaf, tidak ditemukan informasi yang relevan.</p>"

    # 2. LLM RERANKING (via Groq)
    docs_str = "\n".join([f"ID: {d['id']}\nCuplikan: {d['text'][:300]}...\n" for d in combined_docs])

    try:
        print("--- Melakukan Reranking via LLM (Groq) ---")
        rerank_res = rerank_chain.invoke({
            "question": question,
            "docs_list": docs_str
        })

        relevant_ids = [x.strip() for x in rerank_res['text'].split(',')]

        final_docs = [d for d in combined_docs if d['id'] in relevant_ids]

        if not final_docs:
            print("Fallback: Reranking tidak menemukan hasil, menggunakan Top Embedding.")
            final_docs = docs_emb[:3]
        else:
            print(f"LLM Memilih Dokumen: {[d['filename'] for d in final_docs]}")

    except Exception as e:
        print(f"Reranking Error: {e}")
        final_docs = docs_emb[:3]

    # 3. GENERATE ANSWER (Format HTML via Groq)
    context_text = "\n\n".join([f"Sumber: {d['filename']}\nIsi: {d['text']}" for d in final_docs])

    try:
        response = qa_chain.invoke({
            "question": question,
            "context": context_text
        })
        return response['text']

    except Exception as e:
        return f"<p>Error generation: {str(e)}</p>"


def reload_rag():
    load_and_index_documents()
    memory.clear()
