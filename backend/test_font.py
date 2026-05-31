import fitz

doc = fitz.open()
page = doc.new_page()

font_path = "font.ttf"
page.insert_font(fontname="noto", fontfile=font_path)

# Test Hindi with English
text = "यह एक परीक्षण है। A B C O 1 2 3"
rect = fitz.Rect(50, 50, 400, 100)
page.insert_textbox(rect, text, fontsize=12, fontname="noto", color=(0, 0, 0))

doc.save("test_font.pdf")
doc.close()
print("Done!")
