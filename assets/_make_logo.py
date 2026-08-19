"""从 logo_source.png 生成 README 用的透明底 logo。

原图 1024x1024:米色底 + 淡米色圆形光晕 + 小人 + 底部烤进去的"Alear030"字样。
README 头部另有 H1 标题,图里那行字重复,且米色方块在 GitHub 深色主题下是块亮斑。

逐行扫描测得 y=912 整行无内容,是小人与文字带之间的干净切点。
光晕只比背景深约 12 个色阶,要保它得把泛洪容差压到 12 以下,边缘会留大片脏像素,
收益又极低(视觉上几乎看不出),所以连光晕一起去掉,只留小人。
"""
from PIL import Image, ImageDraw

SRC = 'assets/logo_source.png'
DST = 'assets/logo.png'
TEXT_BAND_TOP = 912   # 行扫描测得的切点
TOL = 25              # 泛洪容差:要盖过背景与光晕的 12 色阶差,又不能啃到人物
SENTINEL = (255, 0, 255)
OUT = 512
PAD = 0.06

im = Image.open(SRC).convert('RGB').crop((0, 0, 1024, TEXT_BAND_TOP))

# 四角各泛洪一次:背景是连通的,但四角分别下种可以兜住光晕被判成前景时的分割情况
d = ImageDraw.floodfill
for seed in [(0, 0), (im.width-1, 0), (0, im.height-1), (im.width-1, im.height-1)]:
    d(im, seed, SENTINEL, thresh=TOL)

# 哨兵色转透明。人物配色是米/蓝/黑/白,不含品红,不会误伤
im = im.convert('RGBA')
px = im.load()
for y in range(im.height):
    for x in range(im.width):
        if px[x, y][:3] == SENTINEL:
            px[x, y] = (0, 0, 0, 0)

im = im.crop(im.getbbox())

# 等比缩放后居中垫到方形画布,四周留边距,避免头发贴边
inner = int(OUT * (1 - PAD*2))
im.thumbnail((inner, inner), Image.LANCZOS)
canvas = Image.new('RGBA', (OUT, OUT), (0, 0, 0, 0))
canvas.paste(im, ((OUT-im.width)//2, (OUT-im.height)//2), im)
canvas.save(DST)
print(f'{DST}  {canvas.size[0]}x{canvas.size[1]}  裁后内容 {im.size[0]}x{im.size[1]}')
