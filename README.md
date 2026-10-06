# CS Document Service

خدمة مستقلة يستخدمها موديول **AI Implementation Assistant** في Odoo لـ:

- **تحويل الوورد إلى PDF** بنفس التصميم وبخطوط قوالبك (LibreOffice داخل Docker).
- **تحويل صفحات PDF إلى صور**، حتى يقرأ نموذج الصور (مثل Qwen VL) الملفات الممسوحة ضوئياً.
- **عرض الخطوط المثبتة**، حتى ينبهك Odoo إذا كان خط في قالب وورد غير مثبت.

لا تحتفظ الخدمة بأي ملف: كل طلب يُعالج في مجلد مؤقت يُحذف فوراً بعد انتهائه.

---

## التركيب عبر GitHub و Portainer

### 1. الريبو

- أنشئ ريبو **خاصاً (Private)** على GitHub، مثلاً `cs-document-service`.
- ارفع **محتوى هذا المجلد** إلى جذر الريبو، بحيث يكون `docker-compose.yml` في الجذر.
- ⚠️ **الريبو يجب أن يكون خاصاً** إذا وضعت فيه ملفات الخطوط. خطوط مثل Hacen لها ترخيص، ولا يجوز نشرها علناً.

### 2. الخطوط

عندك طريقتان، اختر واحدة:

| الطريقة | كيف | متى تُحدَّث |
|---|---|---|
| **أ) داخل الريبو** | ضع ملفات `.ttf` و `.otf` في مجلد `fonts/` في الريبو | عند كل إعادة نشر (Pull and redeploy) |
| **ب) على السيرفر** | انسخها إلى `/opt/cs-docservice/fonts` على السيرفر، عبر SFTP مثلاً | بإعادة تشغيل الحاوية فقط، بدون بناء |

الخطوط المطلوبة لقالب جنة باور:
- `Hacen Tunisia`
- `Hacen Tunisia Bold`
- `Hacen Tunisia Lt`
- `UbuntuArabic-Regular` و `UbuntuArabic-Bold`
- `Techno Race`

الخطوط التالية مثبتة مسبقاً:
- خطوط عربية: Noto Naskh و Noto Kufi و Amiri و KacstOne.
- بدائل بنفس المقاسات: Liberation بدل Arial و Times، و Carlito بدل Calibri.

### 3. في Portainer

1. افتح **Stacks** ثم **Add stack**، وسمّه مثلاً `cs-docservice`.
2. اختر **Repository**:
   - **Repository URL:** `https://github.com/<حسابك>/cs-document-service`
   - **Repository reference:** `refs/heads/main`
   - **Compose path:** `docker-compose.yml`
   - **Authentication:** فعّلها، واكتب اسم مستخدم GitHub وتوكن *Personal access token* بصلاحية قراءة الريبو فقط (Fine-grained، صلاحية Contents: Read-only).
3. في **Environment variables** أضف:

   | المتغير | القيمة |
   |---|---|
   | `DOCSERVICE_TOKEN` | توكن طويل عشوائي (إجباري). على أي جهاز لينكس: `openssl rand -hex 32` |
   | `DOCSERVICE_PORT` | المنفذ على السيرفر. الافتراضي 8000 |
   | `FONTS_DIR` | مجلد الخطوط على السيرفر. الافتراضي `/opt/cs-docservice/fonts` |

4. (اختياري) **GitOps updates**: فعّلها حتى يعيد Portainer النشر تلقائياً عند أي تحديث في الريبو.
5. اضغط **Deploy the stack**. البناء الأول يأخذ عدة دقائق لتنزيل LibreOffice.

### 4. التحقق

- في Portainer افتح **Containers** ثم `cs-docservice`، وتحقق أن الحالة **healthy**.
- افتح `http://<IP-السيرفر>:8000/health`. يجب أن يظهر:
  `{"status":"ok","libreoffice":"LibreOffice 7.4...","fonts":...}`

### 5. الأمان

- **الأفضل:** ضع الخدمة خلف HTTPS عبر Nginx Proxy Manager أو Traefik، مثلاً `https://docs.example.com` يوجّه إلى `cs-docservice:8000`. بعدها احذف `ports` من ملف الـ compose، أو اجعل المنفذ داخلياً.
- **أو على الأقل:** اسمح بالمنفذ لعنوان سيرفر Odoo فقط:
  ```bash
  ufw allow from <IP-ODOO> to any port 8000
  ```
- كل الطلبات تحتاج التوكن، ما عدا `/health`.

### 6. الربط مع Odoo

افتح **AI Implementation ← Configuration ← Settings**:

| الإعداد | القيمة |
|---|---|
| Document service URL | `https://docs.example.com` أو `http://IP:8000` |
| Document service token | نفس قيمة `DOCSERVICE_TOKEN` |
| Images & scanned files | مزوّد يدعم الصور، مثل Qwen VL أو Claude |

اضغط **Test connection**. يجب أن تظهر رسالة تحتوي إصدار LibreOffice وعدد الخطوط.

---

## ماذا يستخدمها في Odoo

- **إنشاء العروض والعقود من قالب وورد:** يُنشأ PDF عبر الخدمة. إذا كانت متوقفة، يُستخدم المحوّل المحلي.
- **PDF ممسوح ضوئياً في المحادثة:** تُحوّل صفحاته (حتى 15 صفحة) إلى صور، ثم يقرأها نموذج الصور.
- **تحليل قالب وورد:** إذا كان خط في القالب غير مثبت في الخدمة، يظهر تنبيه في المراجعة.

## الواجهة البرمجية

| الطلب | الوصف |
|---|---|
| `GET /health` | الحالة، وإصدار LibreOffice، وعدد الخطوط |
| `GET /v1/fonts` | قائمة الخطوط المثبتة |
| `POST /v1/convert/pdf` | `file` = وورد أو Excel أو PowerPoint ← ملف PDF |
| `POST /v1/render/png` | `file` = PDF، و `dpi` و `first` و `last` ← `{"page_count", "pages": [base64]}` |

متغيرات إضافية:
- `DOCSERVICE_MAX_MB`: أقصى حجم للملف. الافتراضي 30.
- `DOCSERVICE_TIMEOUT`: أقصى مدة للمعالجة بالثواني. الافتراضي 180.
- `DOCSERVICE_WORKERS`: عدد التحويلات المتزامنة. الافتراضي 2.
