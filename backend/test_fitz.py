import fitz

doc = fitz.open("test_font.pdf") # if it exists? Let's check what's in backend
page = doc[0]
blocks = page.get_text("blocks")
print(blocks[0])
