from io import BytesIO
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image

def export_pdf(story,assets,root):
    buf=BytesIO(); c=canvas.Canvas(buf,pagesize=A4); w,h=A4; c.setTitle(story.title)
    for i,panel in enumerate(story.panels):
        c.setFont('Helvetica-Bold',20); c.drawString(42,h-45,f'Panel {i+1}: {panel.title}')
        asset=assets[i] if i<len(assets) else ''
        if asset.endswith('.png'):
            path=Path(root)/asset.split('/generated/')[-1]
            if path.exists():
                with Image.open(path) as im:
                    iw,ih=im.size; scale=min((w-84)/iw,330/ih); nw,nh=iw*scale,ih*scale
                    c.drawImage(ImageReader(im),42+(w-84-nw)/2,300,width=nw,height=nh,mask='auto')
        else:
            c.setFont('Helvetica',10); c.drawString(42,h-75,'Demo SVG artwork is shown in the web app.')
        y=260
        for label,text in [('Caption',panel.caption),('Narration',panel.narration),('Dialogue',f'{story.character}: "{panel.dialogue}"')]:
            c.setFont('Helvetica-Bold',11); c.drawString(42,y,label); c.setFont('Helvetica',10); c.drawString(42,y-16,text[:130]); y-=45
        c.showPage()
    c.save(); buf.seek(0); return buf
