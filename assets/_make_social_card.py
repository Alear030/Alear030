"""从 AI 生成的无字底板合成 GitHub Social Preview 卡片(1280x640)。

底板是 1536x1024(3:2),小人内容纵向占 y=88..944,上下留白加起来不到 180px,
硬裁成 2:1 会切掉头和脚。所以改为向左补白到 2048x1024 再整体缩到 1280x640:
小人一点不动,左侧文字区反而更宽裕。
补白用左侧背景带的水平镜像——接缝处是完美对称,不会出现断层,
淡六边形底纹也能自然延续。

文字本地合成而非让模型烤进图:字锐利、字号行距可控,以后改标语不用重新生成图。
"""
from PIL import Image, ImageDraw, ImageFont

SRC = 'assets/social-plate-1.png'
DST = 'assets/social-card.png'
OUT_W, OUT_H = 1280, 640

WORDMARK = 'Alear030'
TAGLINE = '自研长程记忆 agent harness'
INK = (43, 74, 99)        # 深板岩蓝,与底板的婴儿蓝同色系但足够深以保证对比度
SUB = (129, 141, 152)

plate = Image.open(SRC).convert('RGB')
pad = plate.height*2 - plate.width          # 补足到 2:1 所差的宽度

canvas = Image.new('RGB', (plate.width+pad, plate.height))
canvas.paste(plate.crop((0, 0, pad, plate.height)).transpose(Image.FLIP_LEFT_RIGHT), (0, 0))
canvas.paste(plate, (pad, 0))
canvas = canvas.resize((OUT_W, OUT_H), Image.LANCZOS)

d = ImageDraw.Draw(canvas)
f_mark = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 116)
f_sub = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 31)

x = 96
# 两行整体垂直居中:先量高度再定起点,不靠手调魔数
h_mark = d.textbbox((0, 0), WORDMARK, font=f_mark)[3]
h_sub = d.textbbox((0, 0), TAGLINE, font=f_sub)[3]
gap = 26
top = (OUT_H - (h_mark + gap + h_sub))//2

d.text((x, top), WORDMARK, font=f_mark, fill=INK)
d.text((x, top+h_mark+gap), TAGLINE, font=f_sub, fill=SUB)

canvas.save(DST)
print(f'{DST}  {canvas.size[0]}x{canvas.size[1]}')
