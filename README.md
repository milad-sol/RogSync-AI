# RogSync AI

سیستم همگام‌سازی هوشمند محصولات ووکامرس. محصول را از فروشگاه مبدأ استخراج می‌کند، با OpenRouter بازنویسی می‌کند، در پنل بررسی می‌شود و به فروشگاه مقصد ارسال می‌شود.

رابط کاربری فارسی و راست‌چین است.

## جریان کار

1. **استخراج** — دسته‌بندی مبدأ را انتخاب کنید، قالب پرامپت همان دسته را بگذارید و محصولات را بکشید.
2. **تولید محتوا** — برای هر محصول قالب پرامپت جداگانه انتخاب می‌شود و یک خروجی فارسی (توضیح کوتاه + توضیح اصلی) ساخته می‌شود.
3. **بررسی** — متن، اسلاگ، کلمات کلیدی، دسته‌بندی مقصد و گالری را ویرایش کنید.
4. **ارسال** — پس از تأیید، محصول به ووکامرس مقصد پوش می‌شود. محصولات متغیر همراه تنوع‌هایشان ارسال می‌شوند.

قیمت‌گذاری در این اپ اولویت نیست؛ تمرکز روی استخراج، کیفیت محتوا و ارسال درست است.

## امکانات

- پرامپت اختصاصی برای هر محصول (لپ‌تاپ، کنسول، هدست و …)
- محصولات متغیر: ترکیب‌های واقعی (رنگ، حافظه و …) به پرامپت AI اضافه می‌شوند تا متن همه تنوع‌ها را پوشش دهد؛ قیمت به مدل داده نمی‌شود
- کلمات کلیدی سراسری با تزریق هوشمند روی متن مرتبط
- گالری تصویر با ترتیب کشیدنی و alt سئو
- تم روشن و تیره
- هشدارها با SweetAlert2

## پیش‌نیازها

- [Docker](https://docs.docker.com/get-docker/) و Docker Compose
- کلید WooCommerce مبدأ و مقصد
- کلید [OpenRouter](https://openrouter.ai)

برای اجرای بدون Docker: Python 3.11+ و Redis.

## اجرا با Docker (پیشنهادی)

دیتابیس داخل Compose همیشه **Postgres** است. Redis و Celery هم همراه اپ بالا می‌آیند.

```bash
cp .env.example .env
docker compose up --build
```

سپس باز کنید: [http://127.0.0.1:8000](http://127.0.0.1:8000)

اگر همین پورت را سرور محلی گرفته باشد، اول آن را متوقف کنید.

```bash
docker compose exec web python manage.py seed_demo_product
```

کلیدهای ووکامرس و OpenRouter را در `.env` یا از داخل اپ در **تنظیمات API** و **تنظیمات هوش مصنوعی** بگذارید.

## ساخت کاربر

کاربر ادمین برای ورود به پنل و [ادمین جنگو](http://127.0.0.1:8000/admin/) لازم است:

```bash
# Docker
docker compose exec web python manage.py createsuperuser

# بدون Docker
python manage.py createsuperuser
```

نام کاربری، ایمیل و رمز را وارد کنید. بعد از ساخت، از همان کاربر در پنل استفاده کنید.

## نصب بدون Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
```

`USE_POSTGRES` را `false` بگذارید تا SQLite استفاده شود.

## اجرای بدون Docker

در سه ترمینال جدا:

```bash
# وب
python manage.py runserver

# Redis
redis-server

# صف AI و ارسال
celery -A rogsync worker -l info
```

## ساختار

| مسیر | نقش |
| --- | --- |
| `sync_app/` | مدل‌ها، ویوها، تسک‌ها و قالب‌های پنل |
| `rogsync/` | تنظیمات Django و Celery |
| `sync_app/prompts.py` | جای‌گذاری پرامپت، تنوع‌ها و تقسیم خروجی AI |

## جای‌گذاری پرامپت

در قالب پرامپت می‌توانید از این توکن‌ها استفاده کنید:

`{product_name}` `{brand}` `{gpu_model}` `{compatibility}` `{reference_url}` `{config_note}` `{seo_keywords}` `{variations}`

خروجی مدل باید دو بخش داشته باشد:

```
[Short Description]
...
[Main Description]
...
```

## دمو

```bash
python manage.py seed_demo_product
# یا با Docker:
docker compose exec web python manage.py seed_demo_product
```

یک محصول ساده و یک محصول متغیر نمونه می‌سازد تا صفحه بررسی را ببینید.
