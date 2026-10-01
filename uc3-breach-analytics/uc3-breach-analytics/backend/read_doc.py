import pdfplumber
with pdfplumber.open(r"..\data\corpus\pdf_digital\collision_000b.pdf") as pdf:
    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
print(text)
