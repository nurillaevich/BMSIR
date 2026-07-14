# BMS IR

Home Assistant uchun **to'liq UI orqali** ishlaydigan IR konditsioner boshqaruvi.
Broadlink universal pultiga **to'g'ridan-to'g'ri IP manzil orqali** ulanadi.

- YAML yozish va restart **shart emas**.
- 1-qadamda faqat pultning **IP manzili** kiritiladi.
- Keyin ishlab chiqaruvchi va model tanlanadi (126 ta brend, 332 ta kod).
- Bir modelga bir nechta kod to'g'ri kelsa — har birini **o'sha yerda IR yuborib test qilasiz**, ishlaganini qoldirasiz.
- Ishlagach, qurilmani **xonaga (area)** joylashtirib saqlaysiz.

Model va kodlar SmartIR ro'yxatidan olingan. Tanlangan kod fayli kerak bo'lganda
SmartIR'dan avtomatik yuklab olinadi va keshlanadi (repo kichik bo'lib qoladi).

---

## YOUR_GITHUB_USERNAME — allaqachon to'ldirilgan
Manifest va LICENSE'da username `nurillaevich` qilib qo'yilgan.

## HACS orqali o'rnatish
1. HACS -> uch nuqta -> **Custom repositories**.
2. Repository: `https://github.com/nurillaevich/BMS-IR`, Type: `Integration` -> ADD.
3. **BMS IR** -> Download -> Home Assistant'ni restart qiling.

## Foydalanish
1. **Settings -> Devices & Services -> Add Integration -> "BMS IR"**.
2. **Nom** + Broadlink pult **IP manzili** (masalan `192.168.1.50`) -> ulanish tekshiriladi.
3. **Ishlab chiqaruvchi** -> **model/kod** tanlanadi.
4. **Test**: signal yuboriladi -> konditsioner javob berdimi?
   - Ha -> saqlash; Yo'q -> keyingi kodni sinash.
5. Ishlagach -> **xona (area)** + ixtiyoriy sensorlar -> **Create**.

Konditsioner darhol qurilma sifatida tanlangan xonada paydo bo'ladi.

## Noma'lum konditsioner — kodni aniqlash

Konditsioneringizning device code'ini bilmasangiz, ishlab chiqaruvchini tanlagach 3 usuldan birini tanlaysiz:

1. **🔍 Avtomatik skan (quvvat sensori bilan)** — konditsioner ulangan smart-plug / quvvat sensorini tanlaysiz. Skript barcha kodlarni navbatma-navbat yuboradi va konditsioner quvvati ko'tarilgan kodni o'zi topadi. To'liq qo'lsiz. (Skandan oldin konditsionerni o'chirib qo'ying.)
2. **👁️ Ketma-ket skan** — kodlar birma-bir avtomatik yuboriladi, siz faqat konditsionerga qarab "ishladi" yoki "keyingisi" bosasiz. Quvvat sensori shart emas.
3. **📝 Qo'lda tanlash** — kodni o'zingiz tanlab sinaysiz.

> Eslatma: Broadlink pult faqat IR yuboradi, qabul qila olmaydi. Shuning uchun to'liq avtomatik aniqlash uchun quvvat sensori (1-usul) kerak; aks holda tasdiqni siz berasiz (2-usul).

## Talablar
- Broadlink pult Broadlink ilovasi orqali Wi-Fi'ga ulangan va HA bilan bir tarmoqda bo'lishi kerak.
- Kodlarni yuklab olish uchun HA'da internet bo'lishi kerak (bir marta, keyin keshlanadi).

## Atributsiya
Model/kod ma'lumotlari [SmartIR](https://github.com/smartHomeHub/SmartIR) loyihasidan
(MIT, Copyright (c) 2019 Vassilis Panos). Bu loyiha mustaqil kod bo'lib, SmartIR
format va kod bazasi bilan mos ishlaydi.
