import os
import base64
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Ensure you have GROQ_API_KEY in your .env file
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def ocr_file(path: str) -> str:
    # Get file extension
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext in (".png",):
        mime = "image/png"
    else:
        raise ValueError("Groq Vision currently supports primarily JPG/PNG images.")

    # Encode image to base64
    base64_image = encode_image(path)
    data_url = f"data:{mime};base64,{base64_image}"

    prompt = """
    Analisis dokumen berikut secara menyeluruh.
    1. Identifikasi konteks utama dokumen (jenis & tujuan).
    2. Ekstrak seluruh teks secara lengkap (pertahankan urutan, format tabel ke teks).
    3. Deskripsikan elemen visual penting (tanda tangan, stempel).
    4. Jangan menambahkan interpretasi. Fokus pada isi asli.
    
    Berikan jawaban dalam format:
    Konteks Dokumen: <penjelasan>
    Isi Dokumen: <hasil OCR>
    """

    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        model="llama-3.2-90b-vision-preview", # Best model for OCR on Groq
    )

    return chat_completion.choices[0].message.content

if __name__ == "__main__":
    path = "C:/Users/USER/Documents/a kerja/pipp/smup/new service/ws/public/upload/69350e14da8085cfd1c6e6ec.png"
    text = ocr_file(path)
    print("=== OCR result ===")
    print(text)