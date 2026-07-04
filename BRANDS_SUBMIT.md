# Integratsiya logosini (ikonка) HA'да ko'rsatish

Home Assistant integratsiya kartochка ikonкаsини **faqat** rasmiy
`home-assistant/brands` bazasidan oladi (brands.home-assistant.io CDN orqali).
Shuning uchun ikonка ko'rinishi uchun uni o'sha bazaga yuborish kerak —
custom_components ичидаги icon.png faylининг o'zи kartochка logosини chiqармайди.

Tayyor fayllar shu repoда: `brands/custom_integrations/bms_smart_ir/`
  - icon.png     (256x256)
  - icon@2x.png  (512x512)

## Qadamlar

1. https://github.com/home-assistant/brands ni **Fork** qiling.
2. Fork'ингизга `custom_integrations/bms_smart_ir/` папка yarating va shu
   repodagi `brands/custom_integrations/bms_smart_ir/` ичидаги 2 faylни
   (icon.png, icon@2x.png) o'sha yerга qo'ying.
3. Commit + push, keyin `home-assistant/brands` ga **Pull Request** oching.
4. PR tasdiqлангач (odатда bir necha kun), HA'да "icon not available" o'rнига
   logo chiqади. HA'ни keyinroq restart qiling / cache tozаланг.

Eslatма: bu faqat ko'rinиш uchun — integratsiya ikonкаsіз ham to'liق ishлайверади.
