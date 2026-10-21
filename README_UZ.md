# bp ombor — sinov MVP

Bu dastlabki ishlaydigan MVP: tovar qo‘shish, rasm, kategoriya/manba, qidiruv, qoldiq, kam qoldi filtri, kirim/chiqim tarixi, PNG hisobot, 3 til va tungi/kunduzgi rejim.

## Muhim
- Ma’lumotlar SQLite bazasida saqlanadi; Render’da doimiy disk kerak.
- Mini App faqat `OWNER_TELEGRAM_ID` ga tegishli Telegram akkauntidan foydalanishga ruxsat beradi.
- Tokenni hech qachon kodga yozmang yoki boshqalarga yubormang.
- Bu MVP: Excel import/export, avtomatik jadval bo‘yicha ogohlantirish, tahrirlash/o‘chirish, backup va kuchli audit keyingi bosqichda qo‘shiladi.
- Telegram ichida ochish uchun HTTPS `WEBAPP_URL` talab qilinadi.
- `DEMO_MODE=true` faqat mahalliy sinov uchun; internetga joylaganda `false` qoldiring.

## 1. Bot yaratish
1. Telegram’da `@BotFather` ni oching.
2. `/newbot` yuboring, nomi va username tanlang.
3. Berilgan tokenni maxfiy saqlang.
4. O‘zingizning Telegram numeric ID’ingizni aniqlang (masalan, ishonchli ID bot orqali), uni `OWNER_TELEGRAM_ID` ga kiriting.

## 2. Serverga joylash
1. Ushbu ZIP’ni kompyuterda oching.
2. Fayllarni o‘zingizning GitHub repository’ingizga joylang.
3. Render’da New → Web Service → repository’ni tanlang.
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Persistent diskni `/opt/render/project/src/data` ga ulang.
7. Environment Variables:
   - `BOT_TOKEN` = BotFather bergan token
   - `OWNER_TELEGRAM_ID` = o‘z Telegram raqamingiz emas, numeric Telegram user ID
   - `WEBAPP_URL` = Render bergan HTTPS URL, masalan `https://sizning-xizmatingiz.onrender.com`
   - `DATA_DIR` = `/opt/render/project/src/data`
   - `DEMO_MODE` = `false`
8. Deploy tugagach `https://.../api/health` ochib `{"ok":true,...}` javobini tekshiring.
9. `@BotFather` ga `/setmenubutton` yuboring, botni tanlang va Web App URL sifatida Render URL’ni kiriting. Yoki botga `/start` yuboring — bot web-app tugmasini chiqaradi.

## 3. Kompyuterda ishga tushirish
Python 3.11+ o‘rnating. Terminalda loyiha papkasiga kiring:
```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\\Scripts\\activate
pip install -r requirements.txt
```
Mahalliy sinov uchun:
```bash
DEMO_MODE=true uvicorn main:app --reload
```
Brauzerda `http://127.0.0.1:8000` ochiladi. Bu demo autentifikatsiyasiz; real internetga bunday holatda qo‘ymang.

## 4. iPhone’dan sinash
Render deploy tugagach Telegram’da botni oching, `/start` yuboring va `bp omborni ochish` tugmasini bosing. Tovar qo‘shib, kirim/chiqim kiritib ko‘ring. PNG hisobotni Tarix bo‘limidan yuklab olish mumkin.

## 5. Hozirgi cheklovlar
- Botga avtomatik low-stock xabarlari va rasmli hisobotni Telegram chatiga avtomatik yuborish hali ulanmagan; hisobot Mini App ichidan PNG sifatida olinadi.
- Katta katalogga mo‘ljallangan qidiruv oddiy SQLite LIKE qidiruvi. 10,000 tovar uchun yetarli, ammo keyin indeks/FTS bilan yaxshilash mumkin.
- O‘zgartirish/o‘chirish, Excel import/export va zaxira nusxa keyingi iteratsiya uchun.
