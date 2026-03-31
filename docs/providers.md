# Provider Reference

## Groq (§7.1)
- **Base URL:** `https://api.groq.com/openai/v1`
- **Auth:** `Authorization: Bearer {GROQ_API_KEY}`
- **Format:** OpenAI-compatible
- **Models:** llama-3.1-8b-instant, llama-3.1-70b-versatile, mixtral-8x7b-32768, gemma2-9b-it
- **Quirk:** Does NOT support logprobs or logit_bias — FreeRelay strips these automatically
- **Free tier:** 30 RPM, 6K TPM, 500K TPD

## Google AI Studio / Gemini (§7.2)
- **Base URL:** `https://generativelanguage.googleapis.com/v1beta/models`
- **Auth:** `?key={GOOGLE_AI_KEY}` query param (NOT Authorization header)
- **Format:** Different from OpenAI — FreeRelay translates both ways
- **Role mapping:** `assistant` → `model`, system messages → `systemInstruction`
- **Models:** gemini-1.5-flash, gemini-1.5-flash-8b, gemini-1.0-pro
- **Free tier:** 15 RPM, 1M TPM, unlimited TPD

## OpenRouter (§7.3)
- **Base URL:** `https://openrouter.ai/api/v1`
- **Auth:** `Authorization: Bearer {OPENROUTER_API_KEY}`
- **Format:** OpenAI-compatible
- **Extra headers:** `HTTP-Referer`, `X-Title` (required)
- **Free models:** Append `:free` to model name
- **Free tier:** 20 RPM, varies

## Together AI (§7.4)
- **Base URL:** `https://api.together.xyz/v1`
- **Auth:** `Authorization: Bearer {TOGETHER_API_KEY}`
- **Format:** OpenAI-compatible
- **Free tier:** 60 RPM

## Mistral AI
- **Base URL:** `https://api.mistral.ai/v1`
- **Auth:** `Authorization: Bearer {MISTRAL_API_KEY}`
- **Format:** OpenAI-compatible
- **Free tier:** Very limited
