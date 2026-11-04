# Clinic Assistant — Report (Asaan zubaan me)

**Kab check kiya:** 6 Oct 2026
**Branch:** feat/assistant
**Kya compare kiya:** `CLINIC_ASSISTANT_ARCHITECTURE.md` ko code ke sath
**Kya kiya:** doc ko code se milaya + poore tests chalaye

---

## Sab se pehle — 1 minute me poora khel

- Code likha ja chuka hai aur **lagbhag sahi hai** ✅
- Lekin **raat ko test chalane pe 3 test fail** hote hain ❌
- Aur ek **bug** hai: bot patient ko aisi date bata sakta hai jis din koi slot khali nahi ❌
- Branch me ek **doosra (marketing) ka kaam** bhi ghus gaya hai jo is doc se related nahi ⚠️

Bas. Neeche har masla simple zubaan me hai — kya hai, kyun hai, aur fix kya hai.

---

# MASLE AUR FIX

## Masla 1 — Raat ko 3 test fail ho jate hain ❌ (sab se zaroori)

**Kya hota hai:**
Test shaam 5 baje ke **baad** chalao to 3 test fail. Subah chalao to pass.

**Kaunse 3 test:**
- `test_open_slot_options_excludes_booked`
- `test_two_phase_same_turn_rejected`
- `test_confirm_next_turn_needs_name_then_books`

**Kyun hota hai (simple):**
Test me doctor ki timing **9 AM se 5 PM** set hai. Jab test shaam **6:52** pe chala, aaj ke saare time nikal chuke the. Test "aaj" ke slots dhoondta hai → khali milta hai → fail.

**Asli error jo aaya:**
- `AssertionError: [] is not true` (file `test_domain.py` line 35, `test_booking_tools.py` line 48)
- `IndexError: list index out of range` (file `test_booking_tools.py` line 78)

**Proof:** Jab time 10 AM set kar ke chalaya, teeno tests **pass** ho gaye.

**Kahan:** `assistant/tests/factories.py` (doctor ki timing), aur tests khud.

**Fix kya karo:**
- Doctor ki timing **00:00 se 23:59** kar do (poora din), **ya**
- Test ko ek **fix time** pe chalao.

---

## Masla 2 — Bot galat din bata sakta hai ❌

**Kya hota hai:**
Patient poochta hai "kab slot khali hai", aur bot aisi date bata deta hai jis din **koi slot khali hi nahi** (jaise aaj shaam ke baad).

**Kyun hota hai:**
Code saari dates list kar deta hai. Ye check hi nahi karta ke us din koi slot bacha hai ya nahi.

**Kahan:** `assistant/services/slots.py` → `next_available_dates()`

**Fix kya karo:**
Sirf wo dates do jahan **0 se zyada slot** khali ho (`open_slot_count > 0`).

---

## Masla 3 — Live test ka record adhoora ⚠️

**Kya hota hai:**
Asli AI ke sath jo live test hota hai, uska record save hota hai — lekin usme sirf time aur result likha hota hai. Ye nahi hota:
- bot ne kaunsa **tool** chalaya
- tool ko kya **argument** diya
- kitne **round** lage
- kitne **tokens** lage

**Kyun masla hai:**
Record dekh ke review karna mushkil. Pata nahi chalta bot ne andar kya kiya.

**Kahan:** `assistant/engine.py` (trace)

**Fix kya karo:**
Trace me tool name, args, result, rounds aur token usage bhi likho.

---

## Masla 4 — Token usage log nahi hota ⚠️ (chhota)

**Kya:** Har message pe kitne token lage, wo kahin log nahi hota.
**Kahan:** `assistant/engine.py`
**Fix:** `usage_metadata` ko log me daalo.

---

## Masla 5 — Bohat se test missing hain ⚠️

**Kya:** Ye cheezein bina test ke hain, isliye bug pakadna mushkil:
- **Cancellation** (cancel karna, confirm karna, ghalat/adhoora ref dena)
- **Security** (injection, secret leak)
- **Plans / config** ke rules
- **API ke errors** (429, 503)
- **Booking** ke extra cases (duplicate, slot taken, past date)

**Fix:** Ye tests likho.

---

## Masla 6 — System check adhoora ⚠️ (chhota)

**Kya:** Warning sirf tab aata hai jab **playground on** ho. Agar clinic enabled ho magar playground off ho, to warning nahi aati.
**Kahan:** `assistant/checks.py`
**Fix:** "config enabled" wala case bhi add karo.

---

## Masla 7 — Admin me 2 field galat editable hain ⚠️ (chhota)

**Kya:** `wa_status` aur `wa_last_error` editable hain. Doc kehta ye **sirf read-only** hone chahiye.
**Kahan:** `assistant/admin.py`
**Fix:** In dono ko `readonly_fields` me daal do.

---

## Masla 8 — .env.example me galat default model ⚠️ (chhota)

**Kya:** `.env.example` me **Groq** ka model likha hai, lekin doc + code **OpenRouter + deepseek-v4.1-flash** kehte hain.
**Kahan:** `.env.example`
**Fix:** Default ko doc/code ke sath match karo.

---

## Masla 9 — Playground URL hamesha khula hai ⚠️ (chhota)

**Kya:** Doc kehta route sirf flag + DEBUG pe on ho. Code me URL hamesha register hai (bas 404 deta hai).
**Kahan:** `assistant/urls.py` + `config/urls.py`
**Fix:** Route ko conditionally mount karo.

---

## Ek alag baat — is branch me doosra kaam bhi hai ⚠️

Is `feat/assistant` branch me **marketing** ka poora kaam bhi aa gaya hai jo is doc se **bilkul related nahi**:
- poori `marketing/` app
- `whatsapp/meta_client.py` me naya `send_template()`
- `catalog` me marketing wale fields

**Fix:** In sab ko **alag branch / PR** me nikaalo, taake ye branch sirf assistant ka rahe.

---

# JO BILKUL THEEK CHAL RAHA HAI ✅

- Database models, migrations, seed plans (A/B/C)
- Secret encryption (`crypto`) — galat key pe error deta hai
- Redis client — fail-close (Redis down ho to 503)
- Engine, quota, session, compaction
- Saare **11 tools**
- Cancel ka **60-minute rule**
- Playground page (quota bars + trace panel)
- Architecture tests (4) — **sab pass**

---

# AB KYA KARO — IS ORDER ME

1. **Test ka time wala masla fix karo** (Masla 1)
2. **Bot galat din na bataye** (Masla 2)
3. **Trace me poori detail add karo** (Masla 3 + 4)
4. **Missing tests likho** (Masla 5)
5. **Chhoti cheezein:** admin, system check, `.env.example` (Masla 6, 7, 8)
6. **Marketing wala kaam alag branch me nikaalo**
