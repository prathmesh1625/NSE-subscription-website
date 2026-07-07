import pdfplumber
import time
import os

pdf_path = r"d:\prathmesh\shares\nse-announcement-downloader\nse-announcement-downloader\storage/pdf/ABB_27052026161915.pdf"

if not os.path.exists(pdf_path):
    print("PDF not found!")
    exit(1)

print("Opening PDF...")
start = time.time()
with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}")
    
    # Test simple extract_text
    print("Extracting text via extract_text()...")
    t0 = time.time()
    text = ""
    for i, page in enumerate(pdf.pages):
        text += page.extract_text() or ""
        print(f"Page {i+1} simple text: {len(text)} chars")
    print(f"Simple extract_text took: {time.time() - t0:.2f} seconds")
    
    # Test extract_tables on page 1
    print("Extracting tables on page 1...")
    t1 = time.time()
    tables = pdf.pages[0].extract_tables()
    print(f"Tables on page 1 extracted: {len(tables)} tables, took {time.time() - t1:.2f} seconds")
