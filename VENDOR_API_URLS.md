# Vendor gateway URLs (inbound)

Our ngrok / public host for **inbound** (vendor calls us):

## Parent bot (all clinics)

```text
POST https://noncasuistic-sibyl-stirless.ngrok-free.dev/api/vendor/parent/ai-reply/
POST https://noncasuistic-sibyl-stirless.ngrok-free.dev/api/vendor/parent/ai-reply
```

Both with/without trailing slash work. Prefer the slash form.

`vendorContext` on that WhatsApp number:

```json
{}
```

HMAC bot secret: `VENDOR_PARENT_BOT_SECRET` in `.env`

## Clinic bot (one clinic)

```text
POST https://noncasuistic-sibyl-stirless.ngrok-free.dev/api/vendor/clinic/ai-reply/
POST https://noncasuistic-sibyl-stirless.ngrok-free.dev/api/vendor/clinic/ai-reply
```

Both with/without trailing slash work. Prefer the slash form.

`vendorContext` example (Fatimiyah):

```json
{ "clinicId": 9 }
```

HMAC bot secret: `VENDOR_CLINIC_BOT_SECRET` in `.env`

## Outbound (we call vendor)

Base URL: `VENDOR_GATEWAY_BASE_URL` in `.env`  
Helper: `assistant.vendor.outbound.send_vendor_message`  
No status poll / status webhook in this phase.

Secrets live only in `.env` (gitignored). Placeholders are in `.env.example`.
