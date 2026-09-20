# 🚀 DheyaAdspowercBot - AdsPower Automation Hub & Management Suite

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Flask-3.1%2B-000000.svg?style=for-the-badge&logo=flask&logoColor=white" alt="Flask" />
  <img src="https://img.shields.io/badge/Selenium-4.20%2B-43B02A.svg?style=for-the-badge&logo=selenium&logoColor=white" alt="Selenium" />
  <img src="https://img.shields.io/badge/Tailwind_CSS-v3.0-38B2AC.svg?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind CSS" />
  <img src="https://img.shields.io/badge/AdsPower-Global_API-5C5CFF.svg?style=for-the-badge" alt="AdsPower" />
</p>

---

## 📖 نظرة عامة | Overview

**DheyaAdspowercBot** هي منصة متكاملة واحترافية لإدارة وأتمتة متصفحات **AdsPower Global** وحسابات التواصل الاجتماعي المتعددة عبر واجهة مستخدم رسومية متطورة (Web Dashboard) ولوحة تحكم شاملة تدعم اللغة العربية.

تجمع المنصة بين إدارة ملفات المتصفحات الافتراضية والنسخ الاحتياطي الدقيق للبيانات (Full Backup & Restore)، مزامنة وإدارة البروكسيات، وتشغيل أتمتة الردود والمراسلات التلقائية على المنصات الكبرى (**Facebook**, **Instagram**, **X/Twitter**, **TikTok**)، بالإضافة إلى عداد تنازلي حي لمتابعة موعد انتهاء خطة واشتراك حساب AdsPower.

---

## ✨ المميزات الرئيسية | Key Features

### 1. 🌐 إدارة ملفات متصفح AdsPower (Browser Profiles Management)
- **التحكم الفردي والجماعي:** فتح، إغلاق، تجميع، وحذف الملفات بنقرة واحدة.
- **النسخ الاحتياطي والاستعادة الشاملة (Full Backup & Restore):**
  - حفظ واستعادة كاملة لكافة بيانات الحساب: **كلمات المرور المحفوظة (Saved Passwords)**، **التخزين المحلي (LocalStorage)**، **قواعد بيانات IndexedDB**، **سجل التصفح (History)**، **المفضلة (Bookmarks)**، **الإضافات (Extensions)**، و**الكوكيز الكاملة (Session & Persistent Cookies)**.
  - حفظ ومطابقة إعدادات البصمة الرقمية والعتاد: **نظام التشغيل (macOS / Windows / Linux)**، **إصدار نواة المتصفح (Chrome 151)**، **User-Agent**، **حجم ودقة الشاشة (Screen Resolution)**، **الخطوط الافتراضية (System Fonts)**، و**معالجات الرسوميات (WebGL Metal / ANGLE Engines)**.
- **مراقبة خطة الاشتراك (Plan & Expiration Tracker):**
  - استخراج حي لطابع انتهاء الرصيد (`balanceDay`).
  - **عداد تنازلي رقمي حي (Live Digital Ticker)** يتناقص بالثواني والدقائق والساعات والأيام.
  - مراقبة سعة الملفات المستهلكة مقابل الحد الأقصى للحساب (مثل: 12 ملف).

### 2. ⚡ أتمتة المنصات المتعددة (Social Media Automation Hub)
- **فيسبوك (Facebook Automation):**
  - فحص التعليقات الجديدة والرد عليها تلقائياً بقوالب مخصصة.
  - إرسال رسائل خاصة عبر مسنجر (Messenger Private DMs) للمستخدمين المتفاعلين.
  - كتابة بشرية ذكية حرفاً بحرف (Human-like typing) مع دعم الرموز التعبيرية (Emojis) واليونيكود بدون أخطاء BMP.
  - نظام منع تكرار الردود (Deduplication) وسجل تاريخي محفوظ لكل بروفايل.
- **إنستغرام (Instagram Automation):**
  - رصد منشورات Reels والمنشورات العادية، والرد على تعليقات المتابعين والعملاء المحتملين.
- **إكس / تويتر (X / Twitter Automation):**
  - التفاعل مع التغريدات ومراقبة الكلمات المفتاحية والرد التلقائي وإرسال الرسائل المباشرة.
- **تيك توك (TikTok Automation):**
  - تفاعل مرن ومشاهدة طبيعية للمقاطع.

### 3. 🛡️ إدارة البروكسيات المتقدمة (Proxy Management)
- **مزامنة ثنائية مع AdsPower:** استيراد كافة البروكسيات المحفوظة في AdsPower بنقرة واحدة.
- **تعيين البروكسيات للملفات:** ربط البروكسي بالبروفايل مباشرة وتحديث الإعدادات داخل متصفح AdsPower.
- **دعم كافة البروتوكولات:** HTTP, HTTPS, SOCKS5 مع دعم المصادقة (Username/Password) والتحقق الجغرافي (Geo-location).

### 4. 🖥️ واجهة مستخدم رقمية حديثة (Modern Web UI)
- تصميم زجاجي عصري (Glassmorphism Dark Theme) مبني بـ **Tailwind CSS** و **Cairo Font** و **FontAwesome 6**.
- تحديثات لحظية عبر الـ Polling التلقائي دون الحاجة لإعادة تحميل الصفحة.
- شارات تنبيه تفاعلية ونوافذ منبثقة تفصيلية وإشعارات Toast منسقة.

---

## 🏗️ هيكلية المشروع | Project Structure

```text
├── adspower_client.py       # عميل AdsPower البرمجي للتحكم بالـ Local API والتخزين المؤقت والبصمات
├── app.py                   # خادم الويب الأساسي (Flask Web Server) والمسارات البرمجية API
├── automation_runner.py     # وسيط تشغيل ومراقبة المهام الخلفية للأتمتة
├── proxy_manager.py         # نظام إدارة ومزامنة واختبار البروكسيات
├── adspower_run_2.py        # سكربت الأتمتة المتقدم للتفاعل مع منشورات فيسبوك ورسائل مسنجر
├── start_dashboard.sh       # سكربت تشغيل لوحة التحكم السريع
├── start_server.sh          # سكربت التشغيل الذاتي مع التحقق من تشغيل AdsPower وتنظيف الأقفال
├── config.example.json      # ملف نموذج الإعدادات
├── requirements.txt         # متطلبات واعتماديات بايثون
├── automations/             # حزمة محركات الأتمتة للمنصات المختلفة
│   ├── base.py              # الفئة الأساسية المشتركة للأتمتة والتحكم في المتصفح
│   ├── hub.py               # مركز إدارة العمال المتزامنين (Multi-profile Workers Hub)
│   ├── facebook.py          # محرك أتمتة فيسبوك
│   ├── instagram.py         # محرك أتمتة إنستغرام
│   ├── twitter.py           # محرك أتمتة إكس / تويتر
│   └── tiktok.py            # محرك أتمتة تيك توك
├── templates/
│   └── index.html           # واجهة لوحة التحكم الرئيسية (HTML5 + Tailwind)
└── static/
    ├── css/
    │   └── style.css        # الأنماط والتنسيقات والتأثيرات البصرية
    └── js/
        └── app.js           # منطق الواجهة الأمامية والعداد التنازلي وإدارة النوافذ
```

---

## ⚙️ المتطلبات الأساسية | Prerequisites

1. **نظام التشغيل:** Linux (Ubuntu/Debian) أو Windows أو macOS.
2. **بايثون:** الإصدار `Python 3.10` أو أحدث.
3. **متصفح AdsPower:** برنامج **AdsPower Global** مثبت ويعمل على الجهاز.
4. **تفعيل الـ Local API في AdsPower:**
   - افتح تطبيق **AdsPower Global**.
   - انتقل إلى **Settings (الإعدادات)** -> **Local API**.
   - فعّل خيار الـ Local API وتأكد من أن المنفذ هو `50325` (الافتراضي).
   - احصل على مفتاح الـ API Key من نفس الصفحة إن رغبت في استخدامه.

---

## 🚀 التثبيت والتشغيل | Installation & Quick Start

### 1. استنساخ المشروع (Clone Repository)
```bash
git clone git@github.com:DheyaAlqaderi/dheyaadspower.git
cd dheyaadspower
```

### 2. إعداد البيئة الافتراضية وتثبيت الحزم (Virtual Environment)
```bash
# إنشاء البيئة الافتراضية
python3 -m venv venv

# تفعيل البيئة الافتراضية
# على Linux/macOS:
source venv/bin/activate
# على Windows:
# .\venv\Scripts\activate

# تثبيت الاعتماديات
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. إعداد ملف الإعدادات (Configuration)
قم بنسخ ملف الإعدادات النموذجي وإنشاء `config.json`:
```bash
cp config.example.json config.json
```
عدّل البيانات في `config.json` حسب حسابك:
```json
{
  "adspower_api_url": "http://127.0.0.1:50325",
  "api_key": "YOUR_LOCAL_API_KEY",
  "default_profile_id": "k1gy4e8h",
  "post_url": "https://www.facebook.com/your-post-url",
  "page_name": "DheyaStore",
  "public_reply_template": "Hello {name}! Thanks for reaching out. Please check your inbox 📩",
  "private_dm_template": "Hi {name}, thank you for your comment! How can we assist you today?",
  "check_interval_seconds": 45,
  "port": 5000
}
```

### 4. تشغيل لوحة التحكم (Run Dashboard)
يمكنك التشغيل المباشر عبر:
```bash
./start_dashboard.sh
```
أو تشغيل بايثون مباشرة:
```bash
python3 app.py
```
ثم افتح متصفحك على الرابط:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🖱️ التشغيل الذاتي بنقرة واحدة (Desktop Launcher Script)

يحتوي المشروع على سكربت فائق الذكاء [`start_server.sh`](file:///home/ukal/py_workspace/ukal/start_server.sh) يقوم تلقائياً بـ:
1. تنظيف أي أقفال عالقة لتطبيق AdsPower (`SingletonLock`).
2. التحقق مما إذا كان AdsPower يعمل، وتشغيله تلقائياً إذا كان مغلقاً.
3. إنهاء أي نسخة سابقة من الخادم وتشغيل الخادم الجديد في الخلفية كخدمة مستقلة (`setsid daemon`).
4. فتح نافذة متصفح Chrome تلقائياً على لوحة التحكم فور جاهزية الخادم.

لتشغيله:
```bash
chmod +x start_server.sh
./start_server.sh
```

---

## 📡 واجهات البرمجة المتاحة | API Endpoints Reference

| المسار (Endpoint) | الطريقة (Method) | الوصف |
|---|---|---|
| `/` | `GET` | تحميل واجهة لوحة التحكم الرئيسية Dashboard |
| `/api/status` | `GET` | حالة النظام، اتصال AdsPower، العمال النشطين، وبيانات الخطة والعداد |
| `/api/adspower/plan` | `GET` | تفاصيل اشتراك AdsPower الدقيقة، طابع الوقت، وموعد الانتهاء |
| `/api/profiles` | `GET` | جلب قائمة ملفات المتصفح مع البروكسيات والمجموعات |
| `/api/profiles/start` | `POST` | تشغيل بروفايل أو أكثر متزامناً عبر AdsPower |
| `/api/profiles/stop` | `POST` | إيقاف بروفايل معين أو كافة البروفايلات النشطة |
| `/api/profiles/export` | `GET` | تنزيل نسخة احتياطية شاملة لملف معين أو كافة الملفات |
| `/api/profiles/import` | `POST` | استيراد نسخة احتياطية وتطبيق البصمة والبيانات والكوكيز |
| `/api/proxies` | `GET` / `POST` | إدارة قائمة البروكسيات المحلية والمزامنة |
| `/api/proxies/sync` | `POST` | مزامنة البروكسيات المحفوظة من داخل تطبيق AdsPower |
| `/api/proxies/assign` | `POST` | تعيين بروكسي لبروفايل معين وتحديثه في AdsPower |
| `/api/automation/start` | `POST` | بدء الأتمتة المتزامنة لعدة منصات وملفات |
| `/api/automation/stop` | `POST` | إيقاف الأتمتة |
| `/api/automation/logs` | `GET` | جلب السجلات الحية لعمليات الردود والمراسلات |

---

## 🛠️ حل المشاكل الشائعة | Troubleshooting

- **AdsPower غير متصل (Connection Refused):**
  - تأكد من فتح تطبيق AdsPower Global.
  - تحقق من تفعيل خيار **Local API** في إعدادات التطبيق والتأكد من المنفذ `50325`.
- **خطأ في تشغيل AdsPower على Linux:**
  - في حال خروج البرنامج فورياً، احذف ملفات القفل العالقة:
    ```bash
    rm -f ~/.config/adspower_global/Singleton*
    rm -rf /tmp/scoped_dir*
    ```
- **تجاوز حد الملفات المسموحة في AdsPower (12 ملف):**
  - تدعم ميزة الاستيراد في اللوحة خيار **الاستيراد فوق بروفايل حالي (Import over existing profile)** مما يتيح لك استبدال البصمة والكوكيز وتجاوز حد الـ 12 بروفايل دون الحاجة لحذف وإنشاء ملف جديد.

---

## 📜 الترخيص والملكية | License & Author

- **المطور:** ضياء القادري (Dheya Alqaderi)
- **المستودع:** [https://github.com/DheyaAlqaderi/dheyaadspower](https://github.com/DheyaAlqaderi/dheyaadspower)
- مرخص بموجب ترخيص **MIT License**.
