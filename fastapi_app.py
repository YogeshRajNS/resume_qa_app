import os
import fitz
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
import json

with open("api.json","r") as f:
    api=json.load(f)
genai.configure(api_key=api['api_key']) 
print(api['api_key'])

class ResumeExtractor:
    def __init__(self, collection_name="resume_collection"):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.chroma_client = chromadb.PersistentClient(path="./chroma_store")
        self.collection_name = collection_name
        self.collection = self.chroma_client.get_or_create_collection(name=collection_name)

    def pdf_extractor(self, file_path: str):
        pdf_data = fitz.open(file_path)
        data = []
        for page in pdf_data:
            page_number = page.number + 1
            text = page.get_text()
            data.append({"page_number": page_number, "text": text})
        return data

    def create_embeddings(self, pdf_texts):
        for page in pdf_texts:
            text = page["text"]
            embedding = self.model.encode(text)
            page["vector"] = embedding
        return pdf_texts

    def store_to_chromadb(self, data, resume_name):
        for item in data:
            self.collection.add(
                documents=[item["text"]],
                embeddings=[item["vector"]],
                metadatas=[{"page_number": item["page_number"], "resume_name": resume_name}],
                ids=[f"{resume_name}_page_{item['page_number']}"]
            )

    def retrieve(self, query, file_names: List[str], top_k=3):
        query_embedding = self.model.encode(query).tolist()
        if file_names:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"resume_name": {"$in": file_names}},
            )
        else:
            results = self.collection.query(
                query_embeddings=[query_embedding], n_results=top_k
            )

        names = results["ids"][0]
        documents = results["documents"][0]
        data = dict(zip(names, documents))
        return data

    def retrieve_resume_name_list(self):
        results = self.collection.get(include=["metadatas"])
        resume_names = [
            meta.get("resume_name")
            for meta in results["metadatas"]
            if "resume_name" in meta
        ]
        unique_resume_names = sorted(set(resume_names))
        return unique_resume_names

    def delete_resumes(self, resume_names: List[str]):
        results = self.collection.get(include=["metadatas"])
        ids_to_delete = [
            doc_id
            for doc_id, meta in zip(results["ids"], results["metadatas"])
            if meta.get("resume_name") in resume_names
        ]
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
        return ids_to_delete


def answer_with_gemini(query, retrieved_docs):
    context = "\n\n".join(retrieved_docs.values())
    prompt = f"""
You are a helpful assistant. Answer the following question strictly based on the provided resume content.

Resume Content:
{context}

Question:
{query}

Answer:
- Only use information from the resume.
- Avoid adding any outside knowledge.
- Keep answers clear and concise.
- Use bullet points if multiple points exist.
- I want response in markdown
"""
    model = genai.GenerativeModel("models/gemini-1.5-flash")
    response = model.generate_content(prompt)
    return response.text



app = FastAPI()
os.makedirs("./uploads", exist_ok=True)


class QueryRequest(BaseModel):
    resumes: List[str]
    query: str

class DeleteRequest(BaseModel):
    resumes: List[str]




@app.post("/upload_file")
async def upload_file(file: UploadFile = File(...)):
    resume_extractor = ResumeExtractor(collection_name="my_resume_2")

    file_location = f"./uploads/{file.filename}"
    with open(file_location, "wb") as f:
        f.write(await file.read())

    pdf_pages = resume_extractor.pdf_extractor(file_location)
    embedded_pages = resume_extractor.create_embeddings(pdf_pages)
    resume_extractor.store_to_chromadb(embedded_pages, resume_name=file.filename)

    return {"message": f"Resume {file.filename} uploaded successfully!"}


@app.get("/list_resumes")
async def list_resumes():
    resume_extractor = ResumeExtractor(collection_name="my_resume_2")

    resumes = resume_extractor.retrieve_resume_name_list()
    return {"resumes": resumes}


@app.delete("/delete_resumes")
async def delete_resumes(request: DeleteRequest):
    resume_extractor = ResumeExtractor(collection_name="my_resume_2")

    deleted_ids = resume_extractor.delete_resumes(request.resumes)
    return {"deleted_ids": deleted_ids}


@app.post("/query")
async def query_resume(request: QueryRequest):
    resume_extractor = ResumeExtractor(collection_name="my_resume_2")

    results = resume_extractor.retrieve(request.query, file_names=request.resumes)
    answer = answer_with_gemini(request.query, results)
    return answer
