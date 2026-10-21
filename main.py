import os, json, hmac, hashlib, urllib.parse, time, sqlite3, io, asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR","data")); DATA.mkdir(exist_ok=True)
(DB_PATH:=DATA/"bp.sqlite3")
UPLOADS=DATA/"uploads"; UPLOADS.mkdir(exist_ok=True)
TOKEN=os.getenv("BOT_TOKEN","").strip()
OWNER_ID=os.getenv("OWNER_TELEGRAM_ID","").strip()
WEBAPP_URL=os.getenv("WEBAPP_URL","").strip()
DEMO=os.getenv("DEMO_MODE","false").lower()=="true"
def db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(
          id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE, name TEXT NOT NULL,
          category TEXT DEFAULT '', source TEXT DEFAULT '', quantity REAL NOT NULL DEFAULT 0,
          min_quantity REAL NOT NULL DEFAULT 0, unit TEXT DEFAULT 'dona', image TEXT DEFAULT '',
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS movements(
          id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL,
          kind TEXT NOT NULL, quantity REAL NOT NULL, note TEXT DEFAULT '',
          created_at TEXT NOT NULL, FOREIGN KEY(product_id) REFERENCES products(id));
        CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
        CREATE INDEX IF NOT EXISTS idx_movements_date ON movements(created_at);
        """)
def now(): return datetime.now().astimezone().isoformat(timespec="seconds")
def validate_init_data(raw):
    if DEMO and not raw: return True
    if not TOKEN or not raw: return False
    try:
        data=dict(urllib.parse.parse_qsl(raw, keep_blank_values=True))
        got=data.pop("hash",None)
        if not got: return False
        check="\n".join(f"{k}={v}" for k,v in sorted(data.items()))
        secret=hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc,got): return False
        auth=int(data.get("auth_date","0"))
        if abs(time.time()-auth)>86400: return False
        user=json.loads(data.get("user","{}"))
        return bool(OWNER_ID and str(user.get("id"))==OWNER_ID)
    except Exception: return False
async def authorize(req):
    raw=req.headers.get("x-telegram-init-data","")
    if not validate_init_data(raw):
        raise HTTPException(401,"Telegram egasi sifatida tasdiqlanmadi. Bot ichidan oching.")
@asynccontextmanager
async def lifespan(app):
    init_db()
    if TOKEN:
        async def run_bot():
            botapp=Application.builder().token(TOKEN).build()
            async def start(update, context):
                if OWNER_ID and str(update.effective_user.id)!=OWNER_ID:
                    await update.message.reply_text("Kirish ruxsati yo‘q.")
                    return
                if not WEBAPP_URL:
                    await update.message.reply_text("WEBAPP_URL sozlanmagan.")
                    return
                kb=InlineKeyboardMarkup([[InlineKeyboardButton("bp omborni ochish",web_app=WebAppInfo(url=WEBAPP_URL))]])
                await update.message.reply_text("bp ombor tizimi tayyor.",reply_markup=kb)
            botapp.add_handler(CommandHandler("start",start))
            await botapp.initialize(); await botapp.start()
            await botapp.updater.start_polling()
            try:
                while True: await asyncio.sleep(3600)
            finally:
                await botapp.updater.stop(); await botapp.stop(); await botapp.shutdown()
        task=asyncio.create_task(run_bot())
        app.state.bot_task=task
    yield
    task=getattr(app.state,"bot_task",None)
    if task: task.cancel()
app=FastAPI(title="bp warehouse",lifespan=lifespan)
app.mount("/uploads",StaticFiles(directory=str(UPLOADS)),name="uploads")
@app.get("/",response_class=HTMLResponse)
async def home(): return (ROOT/"index.html").read_text(encoding="utf-8")
@app.get("/api/health")
async def health(): return {"ok":True,"app":"bp warehouse"}
@app.get("/api/summary")
async def summary(req:Request):
    await authorize(req)
    with db() as c:
        total=c.execute("SELECT COUNT(*) n FROM products").fetchone()["n"]
        units=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM products").fetchone()["n"]
        low=c.execute("SELECT COUNT(*) n FROM products WHERE quantity<=min_quantity").fetchone()["n"]
        today=datetime.now().astimezone().date().isoformat()
        incoming=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM movements WHERE kind='in' AND substr(created_at,1,10)=?",(today,)).fetchone()["n"]
        outgoing=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM movements WHERE kind='out' AND substr(created_at,1,10)=?",(today,)).fetchone()["n"]
    return dict(total=total,units=units,low=low,incoming=incoming,outgoing=outgoing)
@app.get("/api/products")
async def products(req:Request,q:str="",low_only:bool=False,limit:int=100,offset:int=0):
    await authorize(req)
    limit=max(1,min(limit,250)); offset=max(0,offset)
    with db() as c:
        sql="SELECT * FROM products WHERE (name LIKE ? OR sku LIKE ? OR category LIKE ? OR source LIKE ?)"
        args=[f"%{q}%"]*4
        if low_only: sql+=" AND quantity<=min_quantity"
        sql+=" ORDER BY name LIMIT ? OFFSET ?"; args += [limit,offset]
        rows=[dict(r) for r in c.execute(sql,args).fetchall()]
    return rows
@app.post("/api/products")
async def add_product(req:Request, name:str=Form(...),sku:str=Form(""),category:str=Form(""),source:str=Form(""),quantity:float=Form(0),min_quantity:float=Form(0),unit:str=Form("dona"),image:UploadFile|None=File(None)):
    await authorize(req)
    if not name.strip(): raise HTTPException(400,"Tovar nomini kiriting")
    img=""
    if image and image.filename:
        ext=Path(image.filename).suffix.lower()
        if ext not in {".jpg",".jpeg",".png",".webp"}: raise HTTPException(400,"Rasm JPG, PNG yoki WEBP bo‘lsin")
        content=await image.read()
        if len(content)>5*1024*1024: raise HTTPException(400,"Rasm 5 MB dan kichik bo‘lsin")
        fn=f"{int(time.time()*1000)}_{os.path.basename(image.filename).replace(' ','_')}"
        (UPLOADS/fn).write_bytes(content); img="/uploads/"+fn
    try:
        with db() as c:
            cur=c.execute("INSERT INTO products(sku,name,category,source,quantity,min_quantity,unit,image,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(sku.strip() or None,name.strip(),category.strip(),source.strip(),quantity,min_quantity,unit,img,now()))
            pid=cur.lastrowid
            if quantity>0: c.execute("INSERT INTO movements(product_id,kind,quantity,note,created_at) VALUES(?,?,?,?,?)",(pid,"in",quantity,"Boshlang‘ich qoldiq",now()))
    except sqlite3.IntegrityError: raise HTTPException(400,"Bu tovar kodi allaqachon mavjud")
    return {"ok":True,"id":pid}
@app.post("/api/movement")
async def movement(req:Request,product_id:int=Form(...),kind:str=Form(...),quantity:float=Form(...),note:str=Form("")):
    await authorize(req)
    if kind not in ("in","out") or quantity<=0: raise HTTPException(400,"Harakat turi yoki miqdori noto‘g‘ri")
    with db() as c:
        p=c.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone()
        if not p: raise HTTPException(404,"Tovar topilmadi")
        if kind=="out" and quantity>p["quantity"]: raise HTTPException(400,"Omborda yetarli qoldiq yo‘q")
        newq=p["quantity"]+(quantity if kind=="in" else -quantity)
        c.execute("UPDATE products SET quantity=? WHERE id=?",(newq,product_id))
        c.execute("INSERT INTO movements(product_id,kind,quantity,note,created_at) VALUES(?,?,?,?,?)",(product_id,kind,quantity,note,now()))
        m=c.execute("SELECT id,created_at FROM movements ORDER BY id DESC LIMIT 1").fetchone()
        return {"ok":True,"movement_id":m["id"],"quantity":newq,"name":p["name"],"sku":p["sku"],"unit":p["unit"],"kind":kind,"amount":quantity,"date":m["created_at"],"image":p["image"],"note":note}
@app.get("/api/movements")
async def movements(req:Request,limit:int=100):
    await authorize(req)
    with db() as c:
        return [dict(r) for r in c.execute("""SELECT m.*,p.name,p.sku,p.unit,p.image FROM movements m JOIN products p ON p.id=m.product_id ORDER BY m.id DESC LIMIT ?""",(max(1,min(limit,250)),)).fetchall()]
@app.get("/api/report/{mid}")
async def report(mid:int,req:Request):
    await authorize(req)
    from PIL import Image,ImageDraw,ImageFont
    with db() as c:
        r=c.execute("SELECT m.*,p.name,p.sku,p.unit,p.image,p.category,p.source FROM movements m JOIN products p ON p.id=m.product_id WHERE m.id=?",(mid,)).fetchone()
    if not r: raise HTTPException(404,"Hisobot topilmadi")
    W,H=900,560
    im=Image.new("RGB",(W,H),(5,9,16)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((24,24,W-24,H-24),radius=30,fill=(10,19,31),outline=(0,130,255),width=3)
    try: font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",28); big=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",42)
    except: font=big=ImageFont.load_default()
    d.text((60,55),"bp  |  OMBOR HISOBOTI",font=big,fill=(80,190,255))
    d.text((60,140),f"Tovar: {r['name']}",font=font,fill="white")
    d.text((60,200),f"Kod: {r['sku'] or '-'}",font=font,fill=(180,200,220))
    label="KIRIM" if r["kind"]=="in" else "CHIQIM"
    d.text((60,260),f"{label}: {r['quantity']:g} {r['unit']}",font=big,fill=(50,220,150) if r["kind"]=="in" else (255,100,120))
    d.text((60,340),f"Kategoriya: {r['category'] or '-'}",font=font,fill=(180,200,220))
    d.text((60,390),f"Manba: {r['source'] or '-'}",font=font,fill=(180,200,220))
    d.text((60,450),f"Sana: {r['created_at'][:19].replace('T',' ')}",font=font,fill=(180,200,220))
    d.text((60,500),f"Izoh: {r['note'] or '-'}",font=font,fill=(180,200,220))
    out=io.BytesIO(); im.save(out,format="PNG"); out.seek(0)
    return StreamingResponse(out,media_type="image/png",headers={"Content-Disposition":f'inline; filename="bp-report-{mid}.png"'})
