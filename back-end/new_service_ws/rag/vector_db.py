import chromadb
import os

# 1. Inisialisasi Client (menyimpan data ke folder 'chroma_data')
# Ini akan membuat folder 'chroma_data' secara otomatis
client = chromadb.PersistentClient(path="./chroma_data")

# 2. Membuat atau mendapatkan 'Collection' (seperti tabel di database)
collection = client.get_or_create_collection(name="dokumen_akademik")

def add_document(doc_id, text, metadata):
    """Fungsi untuk menyimpan dokumen ke ChromaDB"""
    collection.add(
        documents=[text],
        metadatas=[metadata],
        ids=[doc_id]
    )

def search_document(query):
    """Fungsi untuk mencari dokumen yang relevan"""
    results = collection.query(
        query_texts=[query],
        n_results=2  # Ambil 2 dokumen paling relevan
    )
    return results