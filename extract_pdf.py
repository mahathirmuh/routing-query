import fitz

doc = fitz.open(r'c:\Users\itsupport\Documents\Apps\KBJFP\tugas.pdf')
for i, page in enumerate(doc):
    print(f"=== PAGE {i+1} ===")
    print(page.get_text())
