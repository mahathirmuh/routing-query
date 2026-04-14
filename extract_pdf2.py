import fitz

doc = fitz.open(r'c:\Users\itsupport\Documents\Apps\KBJFP\tugas.pdf')
print(f"Total pages: {len(doc)}")

for i, page in enumerate(doc):
    text = page.get_text()
    print(f"\n=== PAGE {i+1} ===")
    print(f"Text length: {len(text)}")
    print(f"Text: '{text[:500]}'")
    
    # Check for images
    images = page.get_images()
    print(f"Images on page: {len(images)}")
    
    # Extract page as image for viewing
    pix = page.get_pixmap(dpi=200)
    pix.save(f"page_{i+1}.png")
    print(f"Saved page_{i+1}.png")
