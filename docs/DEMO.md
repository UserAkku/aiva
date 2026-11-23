# Demo guide (showing AIVA to sir 🎓)

## 30 minutes before

1. `make run` and open <http://localhost:8000> in **Chrome** (best echo cancellation).
2. Settings → **Demo readiness check → Deep**. Everything should be green; fix any red.
3. Usage & limits: confirm each provider has plenty of today's quota left. If you rehearsed
   a lot today, add another free key (Gemini / Mistral) — the router uses it automatically.
4. Allow the microphone when the browser asks. Do one test sentence.
5. Mac volume ~60%. Prefer headphones-free demo? Keep the laptop speaker away from the mic
   and leave **barge-in** on (Chrome cancels AIVA's own voice).
6. Close other heavy apps (8 GB RAM).

## A 5-minute script

| # | Say / do | Shows |
|---|---|---|
| 1 | Click **Face lab → dance**, then say *"Hi AIVA, sir ko apna introduction do"* | Face, voice, personality, Hinglish |
| 2 | *"1 से 30 तक गिनती करो"* | Tool that speaks directly (no tokens wasted) |
| 3 | *"Aaj Delhi ka weather kaisa hai?"* | Live data tool + emotion change |
| 4 | Interrupt her mid-sentence: *"Ruko ruko, ek joke sunao"* | Barge-in |
| 5 | *"Make a PDF on Newton's laws for class 9"* | PDF created & opened in Preview |
| 6 | *"YouTube pe lofi music chalao"* | Acting on the Mac |
| 7 | *"Mera inbox check karo"* → *"Sharma sir ko thank-you mail bhejo"* → *"haan bhej do"* | Gmail + safety confirmation |
| 8 | *"Kitni free limit bachi hai?"* | Quota awareness |
| 9 | Show **Usage & limits** and **Activity** pages | Under the hood: router, latency, tools |
| 10 | Show **Hardware** page | Phase 2 plan, wiring, xiaozhi firmware |

## If something goes wrong

| Symptom | Fix |
|---|---|
| "Speech-to-text isn't working" | Groq key missing/exhausted → add a Mistral key (Voxtral fallback) |
| Robot voice sounds different (macOS voice) | Edge TTS unreachable; it retries automatically after 60 s |
| AIVA cuts herself off | Speaker too loud / too close → lower volume or turn off barge-in in Settings |
| AIVA doesn't stop listening | Noisy room → raise *Speech sensitivity* in Settings |
| "All my AI providers are busy" | Every free quota used: add another provider key on Connectors |
| Typed text works but voice doesn't | Check the mic permission (padlock icon in the address bar) |
