# BMS Smart IR (Broadlink + Tuya)

Home Assistant uchun **yagona** IR integratsiya. O'rnatib, qurilma qo'shganda
avval **qaysi usul** ekanini so'raydi:

- **Broadlink** — mahalliy universal pult (IP orqali), SmartIR kod bazasi bilan.
- **Tuya** — Z100 kabi Tuya/Zigbee IR hub, **bulut** orqali (BMS akkauntini
  qayta ishlatadi). Konditsioner → climate; TV/pristavka/ventilyator → remote + tugmalar.

Ya'ni ikkita alohida integratsiya (`bms_ir` va `bms_ir_tuya`) o'rniga — bittasi.


> **Yangi (v1.1.0):** Broadlink orqali qo'shishda endi **Konditsioner** yoki **Televizor** tanlash mumkin. Televizor `media_player` qurilma sifatida (yoq/o'chir, ovoz, kanal, manba) qo'shiladi. TV kodlari [SmartIR media_player](https://github.com/smartHomeHub/SmartIR/blob/master/docs/MEDIA_PLAYER.md) bazasidan olinadi.

## O'rnatish (HACS)

1. Bu repo fayllarini GitHub'ga yuklang (masalan `nurillaevich/bms-smart-ir`).
2. GitHub'da **Release** yarating (tag `v1.0.0`).
3. HACS → Custom repositories → repo URL, Type **Integration** → ADD → Download → Restart.

> Yoki `custom_components/bms_smart_ir` papkasini qo'lda `/config/custom_components/` ga ko'chiring.

## Foydalanish

**Settings → Devices & Services → Add Integration → "BMS Smart IR"**, so'ng menyudan tanlang:

**Broadlink** tanlasangiz:
1. Nom + Broadlink IP manzili (masalan `192.168.1.50`).
2. Ishlab chiqaruvchi → model/kod (avtomatik skan, ketma-ket yoki qo'lda).
3. Test → ishlaganini qoldiring → xona tanlab saqlang.

**Tuya** tanlasangiz:
1. IR hub ID'si (masalan `bf9607ebbc40a65949aeuv`).
2. Ro'yxatdan pultni tanlang (yonida kategoriyasi yozilgan).
3. Test signali yuboriladi → yakunlang.

Har ikkisida ham YAML yo'q, har qurilmaga restart yo'q.

## Talablar

- **Broadlink uchun**: Broadlink pult Wi-Fi'da, HA bilan bir tarmoqda. Kodlar
  birinchi ishlatilganda SmartIR'dan yuklab olinadi (keyin keshlanadi).
- **Tuya uchun**: `bms_integration` Tuya bulut akkauntи bilan sozlangan, va Tuya
  loyihangizda **IR API yoqilgan**.

## Eski integratsiyalar

Bu integratsiya `BMSIR` va `BMSIRTUYA`'ning o'rnini bosadi. Qurilmalar **ikki
marta** chiqmasligi uchun eski ikkalasini (yoki `bms_ir_ac.yaml` ni) olib tashlang.

## Litsenziya

MIT. SmartIR kod bazasi ma'lumotlari [SmartIR](https://github.com/smartHomeHub/SmartIR)
(MIT, © 2019 Vassilis Panos) formatiga mos.
